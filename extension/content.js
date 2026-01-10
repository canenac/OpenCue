/**
 * OpenCue - Content Script
 *
 * Multi-platform support for:
 * 1. Netflix
 * 2. Disney+
 *
 * Features:
 * - Detect video playback
 * - Extract subtitle/caption data
 * - Apply audio muting based on overlay commands
 * - (Future) Apply visual blur overlays
 */

// Platform configurations
const PLATFORMS = {
  netflix: {
    name: 'Netflix',
    hostPattern: /netflix\.com/i,
    subtitleSelectors: [
      // Current Netflix subtitle selectors (2024+)
      '.player-timedtext-text-container span',
      '.player-timedtext span',
      '[data-uia="player-timedtext"] span',
      // Alternative/fallback selectors
      '.player-timedtext-text-container',
      '[class*="player-timedtext"] span',
      '[class*="timedtext"] span'
    ],
    subtitleContainerCheck: (node) => {
      return node.classList?.contains('player-timedtext-text-container') ||
             node.classList?.contains('player-timedtext') ||
             node.getAttribute?.('data-uia') === 'player-timedtext';
    },
    getContentId: () => {
      const match = window.location.pathname.match(/\/watch\/(\d+)/);
      return match ? `netflix:${match[1]}` : 'netflix:unknown';
    }
  },
  disneyplus: {
    name: 'Disney+',
    hostPattern: /disneyplus\.com/i,
    subtitleSelectors: [
      // Disney+ uses Shaka Player for subtitles
      '.shaka-text-container span',
      '.shaka-text-container div',
      '[data-testid="web-player"] .shaka-text-container *',
      // Alternative subtitle containers
      '.btm-media-overlays-container span',
      '.btm-media-client-element span'
    ],
    subtitleContainerCheck: (node) => {
      return node.classList?.contains('shaka-text-container') ||
             node.classList?.contains('btm-media-overlays-container') ||
             node.closest?.('.shaka-text-container');
    },
    getContentId: () => {
      // Disney+ URL format: /video/{contentId}
      const match = window.location.pathname.match(/\/video\/([a-zA-Z0-9-]+)/);
      return match ? `disneyplus:${match[1]}` : 'disneyplus:unknown';
    }
  }
};

// Detect current platform
function detectPlatform() {
  const hostname = window.location.hostname;
  for (const [key, config] of Object.entries(PLATFORMS)) {
    if (config.hostPattern.test(hostname)) {
      return { key, config };
    }
  }
  return null;
}

const currentPlatform = detectPlatform();

if (!currentPlatform) {
  console.log('[OpenCue] Unsupported platform:', window.location.hostname);
} else {
  console.log(`[OpenCue] Content script loaded on ${currentPlatform.config.name}`);
}

// Audio buffer configuration
const AUDIO_BUFFER_MS = 1500; // Delay audio by 1.5 seconds to allow analysis time

// State
let videoElement = null;
let isActive = true;
let pendingOverlays = [];
let subtitleObserver = null;

// Audio delay buffer state
let audioContext = null;
let delayNode = null;
let sourceNode = null;
let audioBufferEnabled = false;

// Subtitle delay state
let subtitleQueue = [];
let subtitleOverlay = null;
let subtitleDelayEnabled = false;
let pendingReplacements = new Map(); // Track word replacements to apply

// Cue file mode state
let sessionMode = 'realtime'; // 'realtime', 'cue_file', 'hybrid', or 'recording'
let syncState = 'idle'; // 'idle', 'syncing', 'synced', 'lost'
let activeCues = new Map(); // Currently active cue overlays
let positionReportInterval = null;
let syncStatusIndicator = null;

// Recording mode state
let isRecording = false;
let recordingOverlay = null;
let recordingCueCount = 0;
let recordingStartTime = null;
let recordingTimerInterval = null;

// Wake lock to prevent sleep during recording
let wakeLock = null;

// Buffering detection
let lastSubtitleTime = 0;
let bufferingCheckInterval = null;
let isBuffering = false;

/**
 * Find the video element
 */
function findVideoElement() {
  const video = document.querySelector('video');
  if (video && video !== videoElement) {
    videoElement = video;
    console.log('[OpenCue] Video element found');

    // Set up subtitle delay FIRST (before observer starts detecting subtitles)
    setupSubtitleDelay();

    // Then set up other systems
    setupVideoListeners();
    setupSubtitleObserver();
    setupAudioBuffer();

    // Create sync status indicator
    createSyncStatusIndicator();

    // Start position reporting for cue file mode
    startPositionReporting();

    return true;
  }
  return !!videoElement;
}

/**
 * Set up audio delay buffer using Web Audio API
 * This delays audio by AUDIO_BUFFER_MS to give time for subtitle analysis
 */
function setupAudioBuffer() {
  if (!videoElement || audioBufferEnabled) return;

  console.log('[OpenCue] Attempting to set up audio buffer...');

  try {
    // Create audio context
    audioContext = new (window.AudioContext || window.webkitAudioContext)();
    console.log('[OpenCue] AudioContext created, state:', audioContext.state);

    // Try to create source from video element
    // NOTE: This will likely FAIL on Netflix due to DRM/CORS restrictions
    sourceNode = audioContext.createMediaElementSource(videoElement);
    console.log('[OpenCue] MediaElementSource created successfully');

    // Create delay node
    delayNode = audioContext.createDelay(AUDIO_BUFFER_MS / 1000 + 0.5);
    delayNode.delayTime.value = AUDIO_BUFFER_MS / 1000;

    // Create gain node for muting
    window.openCueGainNode = audioContext.createGain();
    window.openCueGainNode.gain.value = 1.0;

    // Connect: source -> delay -> gain -> destination
    sourceNode.connect(delayNode);
    delayNode.connect(window.openCueGainNode);
    window.openCueGainNode.connect(audioContext.destination);

    audioBufferEnabled = true;
    console.log(`[OpenCue] Audio buffer ENABLED: ${AUDIO_BUFFER_MS}ms delay`);
    console.log('[OpenCue] WARNING: Audio buffer may not work with DRM-protected content');

  } catch (e) {
    console.log('[OpenCue] Audio buffer FAILED:', e.message);
    console.log('[OpenCue] This is expected for DRM-protected content (Netflix, Disney+)');
    console.log('[OpenCue] Falling back to direct muting (no delay buffer)');
    audioBufferEnabled = false;
  }
}

/**
 * Set up subtitle delay system to sync with audio buffer
 */
function setupSubtitleDelay() {
  if (subtitleDelayEnabled) {
    console.log('[OpenCue] Subtitle delay already enabled');
    return;
  }

  console.log('[OpenCue] Setting up subtitle delay system...');

  // Create subtitle overlay element
  createSubtitleOverlay();

  // Hide native subtitles
  hideNativeSubtitles();

  // Start subtitle queue processor
  setInterval(processSubtitleQueue, 50); // Check every 50ms

  subtitleDelayEnabled = true;
  console.log(`[OpenCue] Subtitle delay enabled: ${AUDIO_BUFFER_MS}ms delay`);
}

/**
 * Create our own subtitle overlay element
 */
function createSubtitleOverlay() {
  if (subtitleOverlay && document.contains(subtitleOverlay)) {
    console.log('[OpenCue] Subtitle overlay already exists');
    return;
  }

  subtitleOverlay = document.createElement('div');
  subtitleOverlay.id = 'opencue-subtitle-overlay';
  subtitleOverlay.style.cssText = `
    position: fixed !important;
    bottom: 80px !important;
    left: 50% !important;
    transform: translateX(-50%) !important;
    z-index: 2147483647 !important;
    text-align: center !important;
    pointer-events: none !important;
    max-width: 80% !important;
    font-family: Netflix Sans, Helvetica Neue, Helvetica, Arial, sans-serif !important;
    font-size: 28px !important;
    font-weight: bold !important;
    color: white !important;
    text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.9),
                 -1px -1px 2px rgba(0, 0, 0, 0.9),
                 1px -1px 2px rgba(0, 0, 0, 0.9),
                 -1px 1px 2px rgba(0, 0, 0, 0.9) !important;
    line-height: 1.4 !important;
    padding: 8px 16px !important;
    background: rgba(0, 0, 0, 0.75) !important;
    border-radius: 4px !important;
    display: none !important;
  `;

  // Try to find the Netflix player container for better fullscreen support
  const playerContainer = document.querySelector('.watch-video, .nfp, [data-uia="watch-video"], .VideoContainer') ||
                          document.body;

  playerContainer.appendChild(subtitleOverlay);
  console.log('[OpenCue] Subtitle overlay created and appended to:', playerContainer.className || 'body');
}

/**
 * Hide native platform subtitles with CSS
 * DISABLED: Since DRM blocks audio buffering, we don't need subtitle delay.
 * Instead, we do in-place replacements on native subtitles.
 */
function hideNativeSubtitles() {
  // DISABLED - keep native subtitles visible, do in-place replacements instead
  console.log('[OpenCue] Native subtitles NOT hidden (in-place replacement mode)');
  return;

  // Original code kept for reference:
  /*
  if (!currentPlatform) return;

  const styleId = 'opencue-hide-subtitles';
  if (document.getElementById(styleId)) return;

  const style = document.createElement('style');
  style.id = styleId;

  // Platform-specific CSS to hide native subtitles
  if (currentPlatform.key === 'netflix') {
    style.textContent = `
      .player-timedtext-text-container,
      .player-timedtext,
      [data-uia="player-timedtext"] {
        visibility: hidden !important;
        opacity: 0 !important;
      }
    `;
  } else if (currentPlatform.key === 'disneyplus') {
    style.textContent = `
      .shaka-text-container,
      .btm-media-overlays-container {
        visibility: hidden !important;
        opacity: 0 !important;
      }
    `;
  }

  document.head.appendChild(style);
  console.log('[OpenCue] Native subtitles hidden');
  */
}

/**
 * Create sync status indicator in corner of video
 */
function createSyncStatusIndicator() {
  if (syncStatusIndicator && document.contains(syncStatusIndicator)) {
    return;
  }

  syncStatusIndicator = document.createElement('div');
  syncStatusIndicator.id = 'opencue-sync-status';
  syncStatusIndicator.style.cssText = `
    position: fixed !important;
    top: 20px !important;
    right: 20px !important;
    z-index: 2147483647 !important;
    padding: 8px 12px !important;
    border-radius: 4px !important;
    font-family: Netflix Sans, Helvetica Neue, Helvetica, Arial, sans-serif !important;
    font-size: 12px !important;
    font-weight: bold !important;
    color: white !important;
    background: rgba(0, 0, 0, 0.7) !important;
    pointer-events: none !important;
    opacity: 0 !important;
    transition: opacity 0.3s !important;
  `;

  const playerContainer = document.querySelector('.watch-video, .nfp, [data-uia="watch-video"], .VideoContainer') ||
                          document.body;
  playerContainer.appendChild(syncStatusIndicator);
  console.log('[OpenCue] Sync status indicator created');
}

/**
 * Update sync status indicator
 */
function updateSyncStatus(state, info = {}) {
  if (!syncStatusIndicator) return;

  // Hide sync status during recording mode - recording has its own overlay
  if (isRecording || sessionMode === 'recording') {
    syncStatusIndicator.style.setProperty('display', 'none', 'important');
    return;
  }

  // Show indicator
  syncStatusIndicator.style.setProperty('display', 'block', 'important');
  syncState = state;

  const states = {
    idle: { text: 'OpenCue', color: '#666' },
    syncing: { text: 'Syncing...', color: '#f0a500' },
    synced: { text: '● Synced', color: '#00c853' },
    lost: { text: '○ Lost Sync', color: '#ff5252' },
    connected: { text: '● Connected', color: '#2196f3' },
    disconnected: { text: '○ Disconnected', color: '#ff5252' }
  };

  const stateConfig = states[state] || states.idle;

  syncStatusIndicator.textContent = stateConfig.text;
  syncStatusIndicator.style.setProperty('border-left', `3px solid ${stateConfig.color}`, 'important');
  syncStatusIndicator.style.setProperty('opacity', '1', 'important');

  // Show offset if synced
  if (state === 'synced' && info.offset_ms !== undefined) {
    syncStatusIndicator.textContent += ` (${info.offset_ms > 0 ? '+' : ''}${info.offset_ms}ms)`;
  }

  // Auto-hide after a few seconds (except for important states)
  if (state === 'synced' || state === 'connected') {
    clearTimeout(syncStatusIndicator.hideTimeout);
    syncStatusIndicator.hideTimeout = setTimeout(() => {
      syncStatusIndicator.style.setProperty('opacity', '0.3', 'important');
    }, 3000);
  }
}

/**
 * Start position reporting for cue file mode
 */
function startPositionReporting() {
  if (positionReportInterval) {
    clearInterval(positionReportInterval);
  }

  // Report position every 500ms when in cue file mode
  positionReportInterval = setInterval(() => {
    if (!videoElement || videoElement.paused) return;
    if (sessionMode !== 'cue_file' && sessionMode !== 'hybrid') {
      // Log occasionally to show mode mismatch
      if (Math.random() < 0.02) {
        console.log('[OpenCue] Position NOT sent - mode is:', sessionMode);
      }
      return;
    }

    const positionMs = Math.floor(videoElement.currentTime * 1000);

    // Log position sends periodically
    if (positionMs % 5000 < 600) {
      console.log('[OpenCue] Sending position:', positionMs, 'ms');
    }

    browser.runtime.sendMessage({
      type: 'position',
      payload: {
        position_ms: positionMs,
        content_id: getContentId()
      }
    }).catch((err) => {
      console.log('[OpenCue] Position send failed:', err.message);
    });
  }, 500);

  console.log('[OpenCue] Position reporting started');
}

/**
 * Handle cue start event from backend
 */
function handleCueStart(cue) {
  console.log('[OpenCue] Cue start:', cue.action, cue.word || '', `(${cue.start_ms}-${cue.end_ms}ms)`);

  // Store active cue
  activeCues.set(cue.cue_id, cue);

  // Apply overlay based on action
  switch (cue.action) {
    case 'mute':
      muteAudio(true);

      // Store replacement for subtitles
      if (cue.matched && cue.replacement) {
        const key = cue.matched.toLowerCase();
        pendingReplacements.set(key, cue.replacement);
      }
      break;

    case 'blur':
      // TODO: Apply blur overlay
      console.log('[OpenCue] Blur cue received (not yet implemented)');
      break;

    case 'skip':
      // TODO: Skip to end_ms
      console.log('[OpenCue] Skip cue received (not yet implemented)');
      break;
  }
}

/**
 * Handle cue end event from backend
 */
function handleCueEnd(cueId) {
  const cue = activeCues.get(cueId);
  if (!cue) return;

  console.log('[OpenCue] Cue end:', cue.action, cueId);

  // Remove overlay based on action
  switch (cue.action) {
    case 'mute':
      // Only unmute if no other mute cues are active
      let otherMuteActive = false;
      for (const [id, activeCue] of activeCues) {
        if (id !== cueId && activeCue.action === 'mute') {
          otherMuteActive = true;
          break;
        }
      }
      if (!otherMuteActive) {
        muteAudio(false);
      }
      break;

    case 'blur':
      // TODO: Remove blur overlay
      break;
  }

  activeCues.delete(cueId);
}

/**
 * Handle sync state change from backend
 */
function handleSyncStateChange(state, info = {}) {
  console.log('[OpenCue] Sync state:', state, info);
  updateSyncStatus(state, info);

  // If we lost sync, clear active cues
  if (state === 'lost') {
    for (const [cueId, cue] of activeCues) {
      handleCueEnd(cueId);
    }
    activeCues.clear();
  }
}

/**
 * Handle mode change confirmation from backend
 */
function handleModeSet(result) {
  if (result.success) {
    sessionMode = result.mode;
    console.log('[OpenCue] Mode set to:', sessionMode);

    // Update UI based on mode
    if (sessionMode === 'realtime') {
      updateSyncStatus('connected');
    } else {
      updateSyncStatus('syncing');
    }
  } else {
    console.error('[OpenCue] Failed to set mode:', result.error);
  }
}

/**
 * Handle cue file loaded confirmation from backend
 */
function handleCueFileLoaded(result) {
  if (result.success) {
    console.log('[OpenCue] Cue file loaded, mode:', result.mode, 'cue_count:', result.cue_count);
    sessionMode = result.mode;
    updateSyncStatus('syncing');
    console.log('[OpenCue] sessionMode now:', sessionMode, '- position reporting should be active');
  } else {
    console.error('[OpenCue] Failed to load cue file:', result.error);
    updateSyncStatus('idle');
  }
}

/**
 * Get content title from the page (Netflix/Disney+)
 */
function getContentTitle() {
  if (!currentPlatform) return 'Unknown Title';

  if (currentPlatform.key === 'netflix') {
    // Try multiple selectors for Netflix title
    const titleSelectors = [
      '[data-uia="video-title"]',
      '.video-title',
      '.ellipsize-text',
      'h4.ellipsize-text',
      '.watch-title'
    ];

    for (const selector of titleSelectors) {
      const el = document.querySelector(selector);
      if (el && el.textContent.trim()) {
        return el.textContent.trim();
      }
    }

    // Try to get from page title
    const pageTitle = document.title;
    if (pageTitle && pageTitle.includes('Netflix')) {
      return pageTitle.replace(' | Netflix', '').replace('Netflix - ', '').trim();
    }
  } else if (currentPlatform.key === 'disneyplus') {
    const titleSelectors = [
      '[data-testid="title"]',
      '.title-field',
      'h2.title'
    ];

    for (const selector of titleSelectors) {
      const el = document.querySelector(selector);
      if (el && el.textContent.trim()) {
        return el.textContent.trim();
      }
    }
  }

  // Generic fallback: use page title and clean it up
  const pageTitle = document.title;
  if (pageTitle) {
    // Remove common suffixes like " - Service Name", " | Service Name"
    const cleanTitle = pageTitle
      .replace(/\s*[-|]\s*(Netflix|Disney\+|Hulu|Prime Video|Amazon|HBO Max|Max|Peacock|Paramount\+|Apple TV\+|Crunchyroll|YouTube|Vudu|Tubi|Pluto TV).*$/i, '')
      .replace(/^(Watch|Streaming|Play)\s+/i, '')
      .trim();
    if (cleanTitle && cleanTitle.length > 0) {
      return cleanTitle;
    }
  }

  return 'Unknown Title';
}

/**
 * Create recording overlay to block video during recording
 */
function createRecordingOverlay() {
  if (recordingOverlay && document.contains(recordingOverlay)) {
    return;
  }

  recordingOverlay = document.createElement('div');
  recordingOverlay.id = 'opencue-recording-overlay';
  recordingOverlay.innerHTML = `
    <div class="recording-content">
      <div class="recording-icon">●</div>
      <h2>OpenCue Recording</h2>
      <p id="opencue-recording-title">Recording...</p>
      <div class="recording-stats">
        <span id="opencue-recording-cues">0 cues detected</span>
        <span id="opencue-recording-time">00:00</span>
      </div>
      <div class="recording-status-line">
        <span class="recording-overlay-status">Recording</span>
        <span class="recording-overlay-connection">Connected</span>
      </div>
      <p class="recording-hint">Video is hidden during recording. Computer will not sleep.<br>You can switch tabs or do other things.</p>
    </div>
  `;

  // Inject styles
  const style = document.createElement('style');
  style.id = 'opencue-recording-styles';
  style.textContent = `
    #opencue-recording-overlay {
      position: fixed !important;
      top: 0 !important;
      left: 0 !important;
      width: 100vw !important;
      height: 100vh !important;
      background: rgba(20, 20, 40, 0.95) !important;
      z-index: 2147483647 !important;
      display: flex !important;
      align-items: center !important;
      justify-content: center !important;
      color: white !important;
      font-family: Netflix Sans, Helvetica Neue, Arial, sans-serif !important;
      pointer-events: none !important;
    }
    #opencue-recording-overlay .recording-content {
      text-align: center !important;
      padding: 40px !important;
    }
    #opencue-recording-overlay .recording-icon {
      font-size: 80px !important;
      color: #e50914 !important;
      animation: pulse-recording 1.5s infinite !important;
      margin-bottom: 20px !important;
    }
    @keyframes pulse-recording {
      0%, 100% { opacity: 1; transform: scale(1); }
      50% { opacity: 0.5; transform: scale(1.1); }
    }
    #opencue-recording-overlay h2 {
      font-size: 32px !important;
      margin: 0 0 10px 0 !important;
      font-weight: 600 !important;
    }
    #opencue-recording-overlay #opencue-recording-title {
      font-size: 24px !important;
      color: #ccc !important;
      margin: 0 0 30px 0 !important;
    }
    #opencue-recording-overlay .recording-stats {
      display: flex !important;
      gap: 40px !important;
      justify-content: center !important;
      margin-bottom: 30px !important;
    }
    #opencue-recording-overlay .recording-stats span {
      font-size: 18px !important;
      padding: 10px 20px !important;
      background: rgba(255,255,255,0.1) !important;
      border-radius: 8px !important;
    }
    #opencue-recording-overlay .recording-status-line {
      display: flex !important;
      gap: 20px !important;
      justify-content: center !important;
      margin-bottom: 20px !important;
      font-size: 14px !important;
    }
    #opencue-recording-overlay .recording-overlay-status {
      color: #4CAF50 !important;
      padding: 5px 15px !important;
      background: rgba(76, 175, 80, 0.2) !important;
      border-radius: 4px !important;
    }
    #opencue-recording-overlay .recording-overlay-connection {
      color: #2196F3 !important;
      padding: 5px 15px !important;
      background: rgba(33, 150, 243, 0.2) !important;
      border-radius: 4px !important;
    }
    #opencue-recording-overlay .recording-hint {
      font-size: 14px !important;
      color: #888 !important;
      margin: 0 !important;
      line-height: 1.6 !important;
    }
  `;

  document.head.appendChild(style);
  document.body.appendChild(recordingOverlay);
  console.log('[OpenCue] Recording overlay created');
}

/**
 * Update recording overlay stats
 */
function updateRecordingOverlay(cueCount, elapsedMs, title) {
  if (!recordingOverlay) return;

  const titleEl = recordingOverlay.querySelector('#opencue-recording-title');
  const cuesEl = recordingOverlay.querySelector('#opencue-recording-cues');
  const timeEl = recordingOverlay.querySelector('#opencue-recording-time');

  if (titleEl && title) {
    titleEl.textContent = title;
  }
  if (cuesEl) {
    cuesEl.textContent = `${cueCount} cue${cueCount !== 1 ? 's' : ''} detected`;
  }
  if (timeEl && elapsedMs !== undefined) {
    const mins = Math.floor(elapsedMs / 60000);
    const secs = Math.floor((elapsedMs % 60000) / 1000);
    timeEl.textContent = `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  }
}

/**
 * Remove recording overlay
 */
function removeRecordingOverlay() {
  if (recordingOverlay) {
    recordingOverlay.remove();
    recordingOverlay = null;
  }
  const style = document.getElementById('opencue-recording-styles');
  if (style) {
    style.remove();
  }
  console.log('[OpenCue] Recording overlay removed');
}

/**
 * Start recording mode with countdown
 */
function startRecordingMode(title) {
  console.log('[OpenCue] Starting recording countdown for:', title);

  // Show countdown overlay
  showCountdownOverlay(5, () => {
    // After countdown, activate recording
    console.log('[OpenCue] Countdown complete, activating recording...');
    try {
      activateRecording(title);
      console.log('[OpenCue] Recording activated successfully');
    } catch (err) {
      console.error('[OpenCue] Error activating recording:', err);
    }
  });
}

/**
 * Show countdown overlay before recording starts
 * Uses pointer-events: none so user can still click play
 */
function showCountdownOverlay(seconds, onComplete) {
  // Create countdown overlay - positioned at top, doesn't block clicks
  const overlay = document.createElement('div');
  overlay.id = 'opencue-countdown-overlay';
  overlay.style.cssText = `
    position: fixed;
    top: 20px;
    left: 50%;
    transform: translateX(-50%);
    background: rgba(0, 0, 0, 0.85);
    z-index: 2147483647;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    color: white;
    padding: 30px 50px;
    border-radius: 16px;
    pointer-events: none;
    box-shadow: 0 8px 32px rgba(0,0,0,0.5);
  `;

  const title = document.createElement('div');
  title.style.cssText = 'font-size: 18px; margin-bottom: 10px;';
  title.textContent = 'OpenCue Recording Starting...';

  const countdown = document.createElement('div');
  countdown.style.cssText = 'font-size: 72px; font-weight: bold; color: #4CAF50;';
  countdown.textContent = seconds;

  const instruction = document.createElement('div');
  instruction.style.cssText = 'font-size: 16px; margin-top: 10px; color: #aaa;';
  instruction.textContent = 'Press PLAY now!';

  overlay.appendChild(title);
  overlay.appendChild(countdown);
  overlay.appendChild(instruction);
  document.body.appendChild(overlay);

  let remaining = seconds;
  const interval = setInterval(() => {
    remaining--;
    if (remaining > 0) {
      countdown.textContent = remaining;
    } else {
      clearInterval(interval);
      overlay.remove();
      onComplete();
    }
  }, 1000);
}

/**
 * Request wake lock to prevent computer sleep
 */
async function requestWakeLock() {
  try {
    if ('wakeLock' in navigator) {
      wakeLock = await navigator.wakeLock.request('screen');
      console.log('[OpenCue] Wake lock acquired - computer will not sleep');

      wakeLock.addEventListener('release', () => {
        console.log('[OpenCue] Wake lock released');
      });
    } else {
      console.log('[OpenCue] Wake Lock API not supported');
    }
  } catch (err) {
    console.warn('[OpenCue] Could not acquire wake lock:', err.message);
  }
}

/**
 * Release wake lock
 */
async function releaseWakeLock() {
  if (wakeLock) {
    try {
      await wakeLock.release();
      wakeLock = null;
      console.log('[OpenCue] Wake lock released');
    } catch (err) {
      console.warn('[OpenCue] Error releasing wake lock:', err.message);
    }
  }
}

/**
 * Start buffering detection
 */
function startBufferingDetection() {
  if (bufferingCheckInterval) return;

  bufferingCheckInterval = setInterval(() => {
    if (!videoElement) return;

    // Check if video is buffering (waiting for data)
    const wasBuffering = isBuffering;
    isBuffering = videoElement.readyState < 3 || videoElement.paused;

    if (isBuffering && !wasBuffering) {
      console.log('[OpenCue] Video buffering detected');
      updateRecordingOverlayStatus('Buffering...');
    } else if (!isBuffering && wasBuffering) {
      console.log('[OpenCue] Video resumed from buffering');
      updateRecordingOverlayStatus('Recording');
    }
  }, 1000);
}

/**
 * Stop buffering detection
 */
function stopBufferingDetection() {
  if (bufferingCheckInterval) {
    clearInterval(bufferingCheckInterval);
    bufferingCheckInterval = null;
  }
  isBuffering = false;
}

/**
 * Update recording overlay status text
 */
function updateRecordingOverlayStatus(status) {
  if (recordingOverlay) {
    const statusEl = recordingOverlay.querySelector('.recording-overlay-status');
    if (statusEl) {
      statusEl.textContent = status;
    }
  }
}

/**
 * Activate recording after countdown
 */
function activateRecording(title) {
  console.log('[OpenCue] activateRecording() called with title:', title);

  isRecording = true;
  recordingCueCount = 0;
  recordingStartTime = Date.now();
  sessionMode = 'recording';

  // Hide sync status indicator during recording
  if (syncStatusIndicator) {
    syncStatusIndicator.style.setProperty('display', 'none', 'important');
  }

  // Start timer to update elapsed time every second
  if (recordingTimerInterval) {
    clearInterval(recordingTimerInterval);
  }
  recordingTimerInterval = setInterval(() => {
    if (isRecording && recordingStartTime) {
      const elapsedMs = Date.now() - recordingStartTime;
      updateRecordingOverlay(recordingCueCount, elapsedMs);
    }
  }, 1000);

  // Try to find video element if not already found
  if (!videoElement) {
    console.log('[OpenCue] Video element not found, searching...');
    findVideoElement();
  }

  // Ensure subtitle observer is running
  console.log('[OpenCue] Setting up subtitle observer...');
  setupSubtitleObserver();

  // Request wake lock to prevent sleep
  requestWakeLock();

  // Start buffering detection
  startBufferingDetection();

  // Create blocking overlay
  createRecordingOverlay();
  updateRecordingOverlay(0, 0, title || getContentTitle());

  // NOTE: Do NOT mute the video element during precision recording!
  // VB-Cable handles silent recording by routing audio to a virtual device.
  // If we mute the video, NO audio goes anywhere (not even to VB-Cable).
  // The video stays unmuted but user hears nothing because audio goes to VB-Cable.
  console.log('[OpenCue] Video NOT muted - VB-Cable handles silent recording');

  // Immediately run subtitle debug to see what's on the page
  console.log('[OpenCue] Running immediate subtitle debug...');
  debugFindSubtitles();

  console.log('[OpenCue] Recording mode started - overlay active, video muted, sleep prevented');
}

/**
 * Control video playback (play/pause)
 */
function controlPlayback(action) {
  const video = videoElement || document.querySelector('video');
  if (!video) {
    console.warn('[OpenCue] No video element found for playback control');
    return false;
  }

  if (action === 'pause') {
    video.pause();
    console.log('[OpenCue] Video PAUSED');
    return true;
  } else if (action === 'play') {
    video.play();
    console.log('[OpenCue] Video PLAYING');
    return true;
  }
  return false;
}

/**
 * Stop recording mode
 */
function stopRecordingMode() {
  isRecording = false;
  sessionMode = 'realtime';

  // Stop the recording timer
  if (recordingTimerInterval) {
    clearInterval(recordingTimerInterval);
    recordingTimerInterval = null;
  }
  recordingStartTime = null;

  // Release wake lock
  releaseWakeLock();

  // Stop buffering detection
  stopBufferingDetection();

  // Remove overlay
  removeRecordingOverlay();

  // PAUSE the video when stopping recording (so user can review while processing)
  controlPlayback('pause');

  // Unmute the video (in case it was muted)
  if (videoElement) {
    videoElement.muted = false;
    console.log('[OpenCue] Video unmuted');
  }

  // Also unmute any other videos on page
  const videos = document.querySelectorAll('video');
  videos.forEach(v => v.muted = false);

  console.log('[OpenCue] Recording mode stopped - video paused, wake lock released');
}

/**
 * Handle recording started message
 */
function handleRecordingStarted(payload) {
  if (payload.success) {
    startRecordingMode(payload.title);
  }
}

/**
 * Handle recording stopped message
 */
function handleRecordingStopped(payload) {
  stopRecordingMode();
}

/**
 * Handle recording status update
 */
function handleRecordingStatus(payload) {
  if (payload.recording) {
    recordingCueCount = payload.cue_count || 0;
    updateRecordingOverlay(recordingCueCount, payload.elapsed_ms, payload.title);
  }
}

/**
 * Queue a subtitle for delayed display
 */
function queueSubtitle(text, captureTime) {
  const displayTime = captureTime + AUDIO_BUFFER_MS;

  subtitleQueue.push({
    text: text,
    displayTime: displayTime,
    captureTime: captureTime,
    displayed: false
  });

  console.log(`[OpenCue] Queued subtitle: "${text.substring(0, 30)}..." (display in ${AUDIO_BUFFER_MS}ms, queue size: ${subtitleQueue.length})`);

  // Keep queue manageable
  if (subtitleQueue.length > 50) {
    subtitleQueue = subtitleQueue.slice(-30);
  }
}

/**
 * Process subtitle queue - display subtitles at the right time
 */
function processSubtitleQueue() {
  if (!subtitleDelayEnabled || !subtitleOverlay) return;

  const now = Date.now();
  let latestSubtitle = null;

  for (const item of subtitleQueue) {
    if (item.displayed) continue;

    if (now >= item.displayTime) {
      item.displayed = true;
      latestSubtitle = item;
    }
  }

  if (latestSubtitle) {
    displayDelayedSubtitle(latestSubtitle.text);
  }

  // Clear old items from queue
  subtitleQueue = subtitleQueue.filter(item =>
    !item.displayed || (now - item.displayTime) < 5000
  );
}

/**
 * Display a delayed subtitle with any pending replacements
 */
function displayDelayedSubtitle(text) {
  if (!subtitleOverlay) {
    console.log('[OpenCue] ERROR: No subtitle overlay element!');
    return;
  }

  // Apply any pending replacements
  let displayText = text;
  let replacedCount = 0;

  console.log(`[OpenCue] Processing subtitle: "${text.substring(0, 50)}..." (${pendingReplacements.size} replacements pending)`);

  for (const [matched, replacement] of pendingReplacements) {
    // Keys are lowercase, use case-insensitive regex
    const regex = new RegExp('\\b' + escapeRegex(matched) + '\\b', 'gi');
    const beforeText = displayText;
    displayText = displayText.replace(regex, replacement);
    if (displayText !== beforeText) {
      replacedCount++;
      console.log(`[OpenCue] REPLACED: "${matched}" -> "${replacement}"`);
    }
  }

  if (replacedCount === 0 && pendingReplacements.size > 0) {
    console.log(`[OpenCue] No matches found in text. Pending words: ${Array.from(pendingReplacements.keys()).join(', ')}`);
  }

  console.log(`[OpenCue] Displaying: "${displayText.substring(0, 50)}..."`);
  subtitleOverlay.textContent = displayText;
  subtitleOverlay.style.setProperty('display', 'block', 'important');

  // Auto-hide after 4 seconds if no new subtitle
  clearTimeout(subtitleOverlay.hideTimeout);
  subtitleOverlay.hideTimeout = setTimeout(() => {
    if (subtitleOverlay) {
      subtitleOverlay.style.setProperty('display', 'none', 'important');
    }
  }, 4000);
}

/**
 * Set up listeners on the video element
 */
function setupVideoListeners() {
  if (!videoElement) return;

  videoElement.addEventListener('play', () => {
    console.log('[OpenCue] Video playing');
    sendPlaybackStatus('playing');

    // Resume audio context on play (required by browsers)
    if (audioContext && audioContext.state === 'suspended') {
      audioContext.resume().then(() => {
        console.log('[OpenCue] Audio context resumed');
      });
    }
  });

  videoElement.addEventListener('pause', () => {
    console.log('[OpenCue] Video paused');
    sendPlaybackStatus('paused');
  });

  videoElement.addEventListener('timeupdate', () => {
    checkPendingOverlays();
  });

  videoElement.addEventListener('seeked', () => {
    const positionMs = Math.floor(videoElement.currentTime * 1000);
    console.log('[OpenCue] Video seeked to:', positionMs, 'ms');

    // Clear cues that are no longer valid after seek
    for (const [cueId, cue] of activeCues) {
      if (cue.end_ms <= positionMs || cue.start_ms > positionMs) {
        handleCueEnd(cueId);
      }
    }

    // Notify backend of seek (for cue file mode)
    browser.runtime.sendMessage({
      type: 'playback',
      payload: {
        state: 'seeked',
        content_id: getContentId(),
        position_ms: positionMs
      }
    }).catch(() => {});
  });

  // Detect when video ends (for auto-stop recording)
  videoElement.addEventListener('ended', () => {
    console.log('[OpenCue] Video ended');
    sendPlaybackStatus('ended');

    // Notify sidebar/popup that video has ended
    browser.runtime.sendMessage({
      type: 'videoEnded',
      payload: {
        content_id: getContentId(),
        title: getContentTitle()
      }
    }).catch(() => {});
  });
}

/**
 * Debug function to find subtitles on the page
 */
function debugFindSubtitles() {
  console.log('[OpenCue DEBUG] Searching for subtitles on page...');

  // Try all possible subtitle selectors
  const allSelectors = [
    '.player-timedtext-text-container span',
    '.player-timedtext span',
    '[data-uia="player-timedtext"] span',
    '.player-timedtext-text-container',
    '[class*="timedtext"]',
    '[class*="subtitle"]',
    '[class*="caption"]',
    '.shaka-text-container span',
    // Generic fallbacks
    'div[style*="text-align: center"]',
  ];

  for (const selector of allSelectors) {
    try {
      const elements = document.querySelectorAll(selector);
      if (elements.length > 0) {
        console.log(`[OpenCue DEBUG] Found ${elements.length} elements for: ${selector}`);
        elements.forEach((el, i) => {
          const text = el.textContent?.trim();
          if (text && text.length > 1) {
            console.log(`[OpenCue DEBUG]   ${i}: "${text.substring(0, 50)}"`);
          }
        });
      }
    } catch (e) {}
  }
}

// Run debug every 5 seconds during recording
let debugInterval = null;
function startSubtitleDebug() {
  if (debugInterval) return;
  debugInterval = setInterval(() => {
    if (isRecording) {
      debugFindSubtitles();
    }
  }, 5000);
}

/**
 * Set up MutationObserver to watch for subtitle changes
 */
function setupSubtitleObserver() {
  if (!currentPlatform) return;

  // Disconnect existing observer
  if (subtitleObserver) {
    subtitleObserver.disconnect();
  }

  // Start debug logging
  startSubtitleDebug();

  // Watch for subtitle container to appear
  subtitleObserver = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      if (mutation.type === 'childList') {
        for (const node of mutation.addedNodes) {
          if (node.nodeType === Node.ELEMENT_NODE) {
            checkForSubtitles(node);
          }
        }
      } else if (mutation.type === 'characterData') {
        // Text content changed
        const text = mutation.target.textContent?.trim();
        if (text) {
          handleSubtitleText(text);
        }
      }
    }
  });

  // Start observing the document body
  subtitleObserver.observe(document.body, {
    childList: true,
    subtree: true,
    characterData: true
  });

  console.log('[OpenCue] Subtitle observer started');
}

/**
 * Check a node for subtitle content
 */
function checkForSubtitles(node) {
  if (!currentPlatform || !node.querySelectorAll) return;

  const config = currentPlatform.config;

  // Check using platform-specific selectors
  for (const selector of config.subtitleSelectors) {
    try {
      const elements = node.querySelectorAll(selector);
      for (const el of elements) {
        const text = el.textContent?.trim();
        if (text) {
          handleSubtitleText(text);
        }
      }
    } catch (e) {
      // Selector might not be valid for this node
    }
  }

  // Also check the node itself using platform-specific container check
  if (config.subtitleContainerCheck(node)) {
    const text = node.textContent?.trim();
    if (text) {
      handleSubtitleText(text);
    }
  }

  // For Disney+: also check if node matches selectors directly
  if (currentPlatform.key === 'disneyplus') {
    if (node.classList?.contains('shaka-text-container') ||
        node.closest?.('.shaka-text-container')) {
      const text = node.textContent?.trim();
      if (text) {
        handleSubtitleText(text);
      }
    }
  }
}

/**
 * Handle extracted subtitle text
 */
let lastSubtitleText = '';

function handleSubtitleText(text) {
  // Filter out non-subtitle content
  if (!isValidSubtitle(text)) {
    return;
  }

  // Avoid duplicate sends
  if (text === lastSubtitleText && Date.now() - lastSubtitleTime < 500) {
    return;
  }

  lastSubtitleText = text;
  lastSubtitleTime = Date.now();

  const currentTimeMs = videoElement ? Math.floor(videoElement.currentTime * 1000) : 0;
  const captureTime = Date.now();

  console.log('[OpenCue] Subtitle:', text.substring(0, 50) + (text.length > 50 ? '...' : ''));

  // Queue subtitle for delayed display (synced with audio buffer)
  if (subtitleDelayEnabled) {
    queueSubtitle(text, captureTime);
  }

  // Send to backend for analysis (immediately - we have AUDIO_BUFFER_MS to process)
  sendSubtitle(text, currentTimeMs);
}

/**
 * Filter out non-subtitle content (timestamps, UI text, font tests, etc.)
 */
function isValidSubtitle(text) {
  if (!text || text.length < 2) return false;

  // Filter out timestamps (e.g., "20:50", "1:23:45", "0:13")
  if (/^\d{1,2}:\d{2}(:\d{2})?$/.test(text.trim())) {
    return false;
  }

  // Filter out font test strings (all uppercase/lowercase alphabet sequences)
  if (/^[A-Za-z]{26,}$/.test(text.replace(/\s/g, ''))) {
    return false;
  }

  // Filter out pure numbers
  if (/^\d+$/.test(text.trim())) {
    return false;
  }

  // Filter out single characters or very short non-words
  if (text.length < 3 && !/[a-zA-Z]{2,}/.test(text)) {
    return false;
  }

  // Filter out common Netflix UI elements
  const uiPatterns = [
    /^(Play|Pause|Skip|Next|Previous|Back|Exit|Menu)$/i,
    /^Episode \d+$/i,
    /^Season \d+$/i,
    /^\d+%$/,  // Progress percentages
    /^HD|4K|SDR|HDR$/i
  ];

  for (const pattern of uiPatterns) {
    if (pattern.test(text.trim())) {
      return false;
    }
  }

  return true;
}

/**
 * Send subtitle to backend for analysis
 */
function sendSubtitle(text, startMs) {
  const contentId = getContentId();
  const endMs = startMs + 3000; // Estimate 3 second subtitle duration
  // Include current playback position for 3-step sync
  const positionMs = videoElement ? Math.floor(videoElement.currentTime * 1000) : startMs;

  browser.runtime.sendMessage({
    type: 'subtitle',
    payload: {
      text: text,
      start_ms: startMs,
      end_ms: endMs,
      position_ms: positionMs,  // Current playback position for sync
      content_id: contentId
    }
  }).catch((err) => {
    console.log('[OpenCue] Could not send subtitle:', err.message);
  });
}

/**
 * Send playback status to backend
 */
function sendPlaybackStatus(state) {
  const contentId = getContentId();
  const positionMs = videoElement ? Math.floor(videoElement.currentTime * 1000) : 0;

  browser.runtime.sendMessage({
    type: 'playback',
    payload: {
      state: state,
      content_id: contentId,
      position_ms: positionMs
    }
  }).catch((err) => {
    console.log('[OpenCue] Could not send playback status:', err.message);
  });
}

/**
 * Get content ID from URL (platform-specific)
 */
function getContentId() {
  if (currentPlatform) {
    return currentPlatform.config.getContentId();
  }
  return 'unknown:unknown';
}

/**
 * Handle overlay commands from backend
 */
function handleOverlayCommand(command) {
  console.log('[OpenCue] Overlay command:', command.action, command.start_ms, '-', command.end_ms);

  // If recording, increment cue count and update overlay
  if (isRecording) {
    recordingCueCount++;
    if (recordingStartTime) {
      const elapsedMs = Date.now() - recordingStartTime;
      updateRecordingOverlay(recordingCueCount, elapsedMs);
    }
    console.log('[OpenCue] Recording cue count:', recordingCueCount);
  }

  // Store replacement for subtitle filtering (will be applied when delayed subtitle displays)
  if (command.matched && command.replacement) {
    // Store lowercase key for case-insensitive matching
    const key = command.matched.toLowerCase();
    pendingReplacements.set(key, command.replacement);
    console.log(`[OpenCue] Stored replacement: "${key}" -> "${command.replacement}" (map size: ${pendingReplacements.size})`);

    // Clear replacement after it's no longer needed (after subtitle display delay + buffer)
    setTimeout(() => {
      pendingReplacements.delete(key);
    }, AUDIO_BUFFER_MS + 10000); // Extended to 10s to ensure it covers the delay
  }

  const currentTimeMs = videoElement ? Math.floor(videoElement.currentTime * 1000) : 0;

  // If we're already within the overlay window, apply immediately
  if (currentTimeMs >= command.start_ms && currentTimeMs <= command.end_ms) {
    console.log('[OpenCue] Applying overlay immediately (already in window)');
    applyOverlay(command);
    pendingOverlays.push({
      ...command,
      applied: true
    });
  } else if (currentTimeMs < command.start_ms) {
    // Future overlay - add to pending
    pendingOverlays.push({
      ...command,
      applied: false
    });
  }
  // If currentTimeMs > end_ms, overlay window has passed - ignore

  // Sort by start time
  pendingOverlays.sort((a, b) => a.start_ms - b.start_ms);
}

/**
 * Check and apply pending overlays based on current playback position
 */
function checkPendingOverlays() {
  if (!videoElement || !isActive) return;

  const currentTimeMs = Math.floor(videoElement.currentTime * 1000);

  for (const overlay of pendingOverlays) {
    if (overlay.applied) continue;

    // Check if we're within the overlay window
    if (currentTimeMs >= overlay.start_ms && currentTimeMs <= overlay.end_ms) {
      applyOverlay(overlay);
      overlay.applied = true;
    }

    // Check if overlay has passed
    if (currentTimeMs > overlay.end_ms) {
      removeOverlay(overlay);
      overlay.applied = true;
    }
  }

  // Clean up old overlays
  pendingOverlays = pendingOverlays.filter((o) => !o.applied || currentTimeMs <= o.end_ms);
}

/**
 * Apply an overlay action
 */
function applyOverlay(overlay) {
  switch (overlay.action) {
    case 'mute':
      muteAudio(true);
      // Schedule unmute
      const duration = overlay.end_ms - overlay.start_ms;
      setTimeout(() => {
        muteAudio(false);
      }, duration);

      // Replace subtitle text in native subtitles
      if (overlay.matched && overlay.replacement) {
        replaceSubtitleText(overlay.matched, overlay.replacement);
      }
      break;

    case 'blur':
      // TODO: Implement in Milestone 2.1
      console.log('[OpenCue] Blur not yet implemented');
      break;

    case 'skip':
      // TODO: Implement skip action
      console.log('[OpenCue] Skip not yet implemented');
      break;
  }
}

/**
 * Replace profanity in subtitle text with silly alternative
 */
function replaceSubtitleText(matched, replacement) {
  if (!currentPlatform) {
    console.log('[OpenCue] No platform detected for replacement');
    return;
  }

  const config = currentPlatform.config;
  let foundAny = false;
  let replacedAny = false;

  console.log(`[OpenCue] Looking for "${matched}" to replace with "${replacement}"`);

  // Find all subtitle elements
  for (const selector of config.subtitleSelectors) {
    try {
      const elements = document.querySelectorAll(selector);
      if (elements.length > 0) {
        foundAny = true;
        console.log(`[OpenCue] Found ${elements.length} elements for selector: ${selector}`);
      }
      for (const el of elements) {
        const currentText = el.textContent || '';
        const regex = new RegExp(escapeRegex(matched), 'gi');

        if (regex.test(currentText)) {
          console.log(`[OpenCue] Found match in: "${currentText.substring(0, 50)}..."`);

          if (el.childNodes.length === 1 && el.childNodes[0].nodeType === Node.TEXT_NODE) {
            // Direct text node - replace in text content
            el.textContent = currentText.replace(regex, replacement);
            replacedAny = true;
            console.log(`[OpenCue] Replaced "${matched}" with "${replacement}"`);
          } else if (el.innerHTML) {
            // May have child elements - walk text nodes to replace
            replaceInTextNodes(el, matched, replacement);
            replacedAny = true;
          }
        }
      }
    } catch (e) {
      console.log(`[OpenCue] Error with selector ${selector}:`, e.message);
    }
  }

  if (!foundAny) {
    console.log('[OpenCue] No subtitle elements found on page');
  } else if (!replacedAny) {
    console.log(`[OpenCue] Word "${matched}" not found in current subtitles`);
  }
}

/**
 * Escape special regex characters in a string
 */
function escapeRegex(string) {
  return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Replace text in all text nodes within an element
 */
function replaceInTextNodes(element, matched, replacement) {
  const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT, null, false);
  const regex = new RegExp(escapeRegex(matched), 'gi');

  let node;
  while (node = walker.nextNode()) {
    if (regex.test(node.textContent)) {
      node.textContent = node.textContent.replace(regex, replacement);
      console.log(`[OpenCue] Replaced "${matched}" with "${replacement}"`);
    }
  }
}

/**
 * Remove an overlay action
 */
function removeOverlay(overlay) {
  switch (overlay.action) {
    case 'mute':
      muteAudio(false);
      break;

    case 'blur':
      // TODO: Remove blur overlay
      break;
  }
}

/**
 * Mute/unmute video audio
 */
function muteAudio(shouldMute) {
  if (!videoElement) return;

  // During recording mode with VB-Cable, do NOT mute - audio must flow to VB-Cable
  // VB-Cable routes audio silently; muting stops all audio including to VB-Cable
  if (isRecording) {
    // Don't interfere with audio during precision recording
    return;
  }

  // ALWAYS use video.muted - Web Audio API doesn't work with DRM content (Netflix, Disney+, etc.)
  // The gain node approach fails silently because DRM audio bypasses Web Audio API entirely
  if (shouldMute && !videoElement.muted) {
    videoElement.muted = true;
    console.log('[OpenCue] Audio MUTED');
  } else if (!shouldMute && videoElement.muted) {
    videoElement.muted = false;
    console.log('[OpenCue] Audio UNMUTED');
  }
}

/**
 * Handle messages from background script
 */
browser.runtime.onMessage.addListener((message, sender, sendResponse) => {
  switch (message.type) {
    case 'getTitle':
      // Return the current content title, ID, and duration
      const title = getContentTitle();
      const contentId = getContentId();
      const video = videoElement || document.querySelector('video');
      const durationMs = video && video.duration ? Math.floor(video.duration * 1000) : 0;
      const currentPositionMs = video && video.currentTime ? Math.floor(video.currentTime * 1000) : 0;
      sendResponse({
        title: title,
        contentId: contentId,
        durationMs: durationMs,
        currentPositionMs: currentPositionMs
      });
      break;

    case 'overlay':
      // Overlay command from realtime detection OR cue file mode
      handleOverlayCommand(message.payload);
      sendResponse({ success: true });
      break;

    case 'cue':
      // Individual cue event from cue file mode (via audio sync)
      if (message.payload.event === 'start') {
        handleCueStart(message.payload);
      } else if (message.payload.event === 'end') {
        handleCueEnd(message.payload.cue_id);
      }
      sendResponse({ success: true });
      break;

    case 'cueEnd':
      // Cue end event
      handleCueEnd(message.payload.cue_id);
      sendResponse({ success: true });
      break;

    case 'syncState':
      // Sync state update from audio fingerprint engine
      handleSyncStateChange(message.payload.state, message.payload);
      sendResponse({ success: true });
      break;

    case 'modeSet':
      // Mode change confirmation
      handleModeSet(message.payload);
      sendResponse({ success: true });
      break;

    case 'cueFileLoaded':
      // Cue file loaded confirmation
      handleCueFileLoaded(message.payload);
      sendResponse({ success: true });
      break;

    case 'sessionInfo':
      // Session info update
      console.log('[OpenCue] Session info:', message.payload);
      sessionMode = message.payload.mode || 'realtime';
      sendResponse({ success: true });
      break;

    case 'recordingStarted':
      // Recording started - show overlay, mute video
      handleRecordingStarted(message.payload);
      sendResponse({ success: true });
      break;

    case 'recordingStopped':
      // Recording stopped - remove overlay, unmute video
      handleRecordingStopped(message.payload);
      sendResponse({ success: true });
      break;

    case 'recordingStatus':
      // Recording status update - update overlay display
      handleRecordingStatus(message.payload);
      sendResponse({ success: true });
      break;

    case 'recordingAborted':
      // Recording aborted - remove overlay, unmute video
      stopRecordingMode();
      console.log('[OpenCue] Recording aborted');
      sendResponse({ success: true });
      break;

    // Precision recording handlers (VB-Cable + Whisper mode)
    case 'precisionRecordingStarted':
      // Precision recording started - show overlay, mute video
      handleRecordingStarted(message.payload);
      console.log('[OpenCue] Precision recording started');
      sendResponse({ success: true });
      break;

    case 'precisionRecordingStopped':
      // Precision recording stopped - remove overlay, unmute video
      console.log('[OpenCue] Precision recording stopped - dismissing overlay');
      stopRecordingMode();  // Call directly to ensure overlay is removed
      sendResponse({ success: true });
      break;

    case 'precisionRecordingStatus':
      // Precision recording status update
      handleRecordingStatus(message.payload);
      sendResponse({ success: true });
      break;

    case 'precisionRecordingAborted':
      // Precision recording aborted - remove overlay, unmute video
      stopRecordingMode();
      console.log('[OpenCue] Precision recording aborted');
      sendResponse({ success: true });
      break;

    case 'controlPlayback':
      // Control video playback (play/pause)
      const action = message.payload?.action || message.action;
      const result = controlPlayback(action);
      sendResponse({ success: result, action: action });
      break;

    case 'recordingPaused':
      // Recording paused - keep overlay but update status
      if (message.payload.success) {
        console.log('[OpenCue] Recording paused at', message.payload.state?.position_ms, 'ms');
      }
      sendResponse({ success: true });
      break;

    case 'recordingResumed':
      // Recording resumed - ensure overlay is active
      if (message.payload.success) {
        isRecording = true;
        sessionMode = 'recording';
        console.log('[OpenCue] Recording resumed with', message.payload.existing_cues, 'existing cues');
      }
      sendResponse({ success: true });
      break;

    case 'connectionState':
      console.log('[OpenCue] Backend connection:', message.payload.state);
      if (message.payload.state === 'connected') {
        updateSyncStatus('connected');
      } else if (message.payload.state === 'disconnected') {
        updateSyncStatus('disconnected');
      }
      sendResponse({ success: true });
      break;

    case 'setActive':
      isActive = message.payload.active;
      console.log('[OpenCue] Active state:', isActive);
      if (!isActive) {
        // Remove any active overlays
        muteAudio(false);
        for (const [cueId, cue] of activeCues) {
          handleCueEnd(cueId);
        }
        activeCues.clear();
      }
      sendResponse({ success: true });
      break;

    default:
      console.log('[OpenCue] Unknown message type:', message.type);
      sendResponse({ success: false, error: 'Unknown message type' });
  }

  return true;
});

/**
 * Periodically check for video element (dynamic page loading)
 */
function initVideoDetection() {
  // Initial check
  findVideoElement();

  // Periodic check for video element
  setInterval(() => {
    if (!videoElement || !document.contains(videoElement)) {
      videoElement = null;
      findVideoElement();
    }
  }, 2000);
}

// Initialize if platform is supported
if (currentPlatform) {
  initVideoDetection();
}
