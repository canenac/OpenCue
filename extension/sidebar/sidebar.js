/**
 * OpenCue - Sidebar Script
 *
 * Controls for the persistent sidebar panel.
 * The sidebar stays open while interacting with the page, unlike the popup.
 */

// Elements
const statusDot = document.getElementById('status-dot');
const statusText = document.getElementById('status-text');
const connectBtn = document.getElementById('connect-btn');
const disconnectBtn = document.getElementById('disconnect-btn');
const activityLog = document.getElementById('activity-log');
const modeButtons = document.querySelectorAll('.mode-btn');
const modeDescription = document.getElementById('mode-description');
const cueSection = document.getElementById('cue-section');
const cueFilesList = document.getElementById('cue-files-list');
const syncStatus = document.getElementById('sync-status');
const syncIndicator = document.getElementById('sync-indicator');
const syncText = document.getElementById('sync-text');

// Cue search elements
const currentContentMatch = document.getElementById('current-content-match');
const currentContentTitle = document.getElementById('current-content-title');
const matchedCueFiles = document.getElementById('matched-cue-files');
const cueSearchInput = document.getElementById('cue-search-input');
const cueSearchBtn = document.getElementById('cue-search-btn');

// Recording elements
const recordingSection = document.getElementById('recording-section');
const recordingTitleInput = document.getElementById('recording-title');
const fetchTitleBtn = document.getElementById('fetch-title-btn');
const durationDisplay = document.getElementById('duration-display');
const autoStopCheckbox = document.getElementById('auto-stop-checkbox');
const startRecordingBtn = document.getElementById('start-recording');
const stopRecordingBtn = document.getElementById('stop-recording');
const abortRecordingBtn = document.getElementById('abort-recording');
const recordingStatus = document.getElementById('recording-status');
const pausedStatus = document.getElementById('paused-status');
const recCueCount = document.getElementById('rec-cue-count');
const recFpCount = document.getElementById('rec-fp-count');
const recElapsed = document.getElementById('rec-elapsed');
const recPosition = document.getElementById('rec-position');
const pausedPosition = document.getElementById('paused-position');
const pausedCues = document.getElementById('paused-cues');

// State
let currentState = 'disconnected';
let currentMode = 'recording';  // Default to recording (real-time disabled)
let selectedCueFile = null;
let cueFiles = [];
let matchedFiles = [];  // Files matching current content
let detectedTitle = null;  // Title from current streaming tab
let isRecording = false;
let isPaused = false;
let isProcessing = false;  // Whisper is processing audio
let recordingStartTime = null;
let recordingTimer = null;
let lastRecordingState = null;  // For resume functionality
let precisionRecordingId = null;  // ID from precision recording
let videoDurationMs = 0;  // Duration of current video
let autoStopEnabled = true;  // Auto-stop recording when video ends
const activityItems = [];

// Mode descriptions
const modeDescriptions = {
  realtime: 'Detect profanity from live subtitles',
  cue_file: 'Use pre-analyzed .opencue files with audio sync',
  recording: 'Capture audio silently, transcribe with Whisper for precise cues'
};

/**
 * Update UI based on connection state
 */
function updateConnectionUI(state) {
  currentState = state;

  // Update dot
  statusDot.className = 'dot ' + state;

  // Update text
  const stateLabels = {
    disconnected: 'Disconnected',
    connecting: 'Connecting...',
    connected: 'Connected',
    error: 'Connection Error'
  };
  statusText.textContent = stateLabels[state] || state;

  // Update buttons
  connectBtn.disabled = state === 'connected' || state === 'connecting';
  disconnectBtn.disabled = state === 'disconnected';
}

/**
 * Add activity item to log
 */
function addActivityItem(action, details) {
  // Remove empty state message
  const emptyState = activityLog.querySelector('.empty-state');
  if (emptyState) {
    emptyState.remove();
  }

  // Create activity item
  const item = document.createElement('div');
  item.className = 'activity-item';

  const time = new Date().toLocaleTimeString();
  item.innerHTML = `
    <span class="time">${time}</span>
    <span class="action ${action}">${action}</span>
    <span class="details">${details}</span>
  `;

  // Add to top of log
  activityLog.insertBefore(item, activityLog.firstChild);

  // Keep only last 20 items (more for sidebar since it persists)
  while (activityLog.children.length > 20) {
    activityLog.removeChild(activityLog.lastChild);
  }
}

/**
 * Connect to backend
 */
function connect() {
  updateConnectionUI('connecting');
  browser.runtime.sendMessage({ type: 'connect' }).then((response) => {
    console.log('Connect response:', response);
  }).catch((err) => {
    console.error('Connect error:', err);
    updateConnectionUI('error');
  });
}

/**
 * Disconnect from backend
 */
function disconnect() {
  browser.runtime.sendMessage({ type: 'disconnect' }).then((response) => {
    console.log('Disconnect response:', response);
    updateConnectionUI('disconnected');
  }).catch((err) => {
    console.error('Disconnect error:', err);
  });
}

/**
 * Get initial connection state
 */
function getConnectionState() {
  browser.runtime.sendMessage({ type: 'getConnectionState' }).then((response) => {
    if (response && response.state) {
      updateConnectionUI(response.state);
    }
  }).catch((err) => {
    console.error('Error getting connection state:', err);
  });
}

/**
 * Listen for messages from background script
 */
browser.runtime.onMessage.addListener((message, sender, sendResponse) => {
  switch (message.type) {
    case 'connectionState':
      updateConnectionUI(message.payload.state);
      break;

    case 'cueFileList':
      // Update cue files list
      cueFiles = message.payload.files || [];
      renderCueFiles();
      break;

    case 'cueFileSearchResults':
      // Handle search results
      handleSearchResults(message.payload);
      break;

    case 'syncState':
      // Update sync status
      updateSyncStatusUI(message.payload.state, message.payload);
      break;

    case 'modeSet':
      // Mode change confirmed
      if (message.payload.success) {
        currentMode = message.payload.mode;
        updateModeUI();
      }
      break;

    case 'cueFileLoaded':
      // Cue file loaded
      if (message.payload.success) {
        addActivityItem('loaded', `Cue file: ${selectedCueFile}`);
      }
      break;

    case 'recordingStarted':
    case 'precisionRecordingStarted':
      handleRecordingStarted(message.payload);
      break;

    case 'recordingStopped':
    case 'precisionRecordingStopped':
      handleRecordingStopped(message.payload);
      break;

    case 'precisionRecordingStatus':
      handlePrecisionRecordingStatus(message.payload);
      break;

    case 'precisionRecordingAborted':
      handleRecordingAborted(message.payload);
      break;

    case 'precisionRequirements':
      handlePrecisionRequirements(message.payload);
      break;

    case 'recordingStatus':
      console.log('[OpenCue Sidebar] Received recordingStatus:', message.payload);
      // Only handle old recording system if NOT using precision recording
      if (precisionRecordingId) {
        console.log('[OpenCue Sidebar] Ignoring old recordingStatus - using precision recording');
        break;
      }
      if (message.payload.recording) {
        // Restore recording state if sidebar was opened during recording
        if (!isRecording) {
          isRecording = true;
          currentMode = 'recording';
          updateModeUI();
          // Show recording section
          cueSection.style.display = 'none';
          recordingSection.style.display = 'block';
          // Calculate recordingStartTime from elapsed_ms so timer works correctly
          const elapsedMs = message.payload.elapsed_ms || 0;
          recordingStartTime = Date.now() - elapsedMs;
          startRecordingTimer();
          recordingTitleInput.value = message.payload.title || '';
          console.log('[OpenCue Sidebar] Recording state restored, elapsed:', elapsedMs);
        }
        updateRecordingCueCount(message.payload.cue_count);
        updateRecordingFpCount(message.payload.fingerprint_count || 0);
        updateRecordingUI();
      } else if (isRecording && !precisionRecordingId) {
        // Recording stopped elsewhere (only for old recording system)
        isRecording = false;
        stopRecordingTimer();
        updateRecordingUI();
      }
      break;

    case 'overlay':
      // Log overlay activity and update recording count if recording
      const action = message.payload.action;
      const category = message.payload.category || 'unknown';
      addActivityItem(action, category);

      // If recording, request status update
      if (isRecording) {
        browser.runtime.sendMessage({
          type: 'getRecordingStatus',
          payload: {}
        }).catch(() => {});
      }
      break;

    case 'videoEnded':
      // Video has finished playing - auto-stop recording if enabled
      console.log('[OpenCue Sidebar] Video ended');
      addActivityItem('info', 'Video ended');
      if (isRecording && autoStopEnabled) {
        addActivityItem('info', 'Auto-stopping recording...');
        stopRecording();
      }
      break;
  }

  sendResponse({ received: true });
  return true;
});

/**
 * Set mode
 */
function setMode(mode) {
  currentMode = mode;
  updateModeUI();

  // Show/hide sections based on mode
  if (mode === 'cue_file') {
    cueSection.style.display = 'block';
    recordingSection.style.display = 'none';
    loadCueFiles();
  } else if (mode === 'recording') {
    cueSection.style.display = 'none';
    recordingSection.style.display = 'block';
  } else {
    cueSection.style.display = 'none';
    recordingSection.style.display = 'none';
  }

  // Send mode change to backend (except recording which has its own flow)
  if (mode !== 'recording') {
    browser.runtime.sendMessage({
      type: 'setMode',
      payload: { mode: mode }
    }).catch((err) => {
      console.error('Error setting mode:', err);
    });
  }
}

/**
 * Update mode UI
 */
function updateModeUI() {
  // Update buttons
  modeButtons.forEach((btn) => {
    if (btn.dataset.mode === currentMode) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
  });

  // Update description
  modeDescription.textContent = modeDescriptions[currentMode] || '';
}

/**
 * Load cue files from backend
 */
function loadCueFiles() {
  cueFilesList.innerHTML = '<p class="empty-state">Loading cue files...</p>';

  browser.runtime.sendMessage({
    type: 'listCueFiles',
    payload: {}
  }).catch((err) => {
    cueFilesList.innerHTML = '<p class="empty-state">Failed to load cue files</p>';
  });
}

/**
 * Render cue files list
 */
function renderCueFiles() {
  if (cueFiles.length === 0) {
    cueFilesList.innerHTML = '<p class="empty-state">No cue files found</p>';
    return;
  }

  cueFilesList.innerHTML = '';
  cueFiles.forEach((file) => {
    const item = document.createElement('div');
    item.className = 'cue-file-item' + (file.id === selectedCueFile ? ' selected' : '');
    item.dataset.id = file.id;

    const duration = formatDuration(file.duration_ms);
    const badge = file.has_fingerprints
      ? '<span class="cue-file-badge has-fp">Audio Sync</span>'
      : '<span class="cue-file-badge">Timestamps</span>';

    item.innerHTML = `
      <div class="cue-file-info">
        <div class="cue-file-title">${file.title}</div>
        <div class="cue-file-meta">${file.cue_count} cues - ${duration}</div>
      </div>
      ${badge}
    `;

    item.addEventListener('click', () => selectCueFile(file.id));
    cueFilesList.appendChild(item);
  });
}

/**
 * Select a cue file
 */
function selectCueFile(fileId) {
  selectedCueFile = fileId;
  renderCueFiles();

  // Show sync status
  syncStatus.style.display = 'flex';
  updateSyncStatusUI('syncing', {});

  // Load cue file
  browser.runtime.sendMessage({
    type: 'loadCueFile',
    payload: { id: fileId }
  }).catch((err) => {
    console.error('Error loading cue file:', err);
    updateSyncStatusUI('error', { error: err.message });
  });
}

/**
 * Update sync status UI
 */
function updateSyncStatusUI(state, info = {}) {
  console.log('[OpenCue Sidebar] Sync state:', state, info);
  syncIndicator.className = 'sync-indicator ' + state;

  const stateTexts = {
    idle: 'Not synced',
    syncing: 'Syncing...',
    synced: 'Synced',
    lost: 'Lost sync',
    error: 'Error'
  };

  let text = stateTexts[state] || state;
  if (state === 'syncing' && info.mode === 'subtitle') {
    text = 'Waiting for subtitles...';
  } else if (state === 'synced') {
    if (info.mode === 'timestamp') {
      text = 'Ready (timestamp mode)';
    } else if (info.mode === 'subtitle') {
      text = 'Synced via subtitles';
      if (info.confidence !== undefined) {
        text += ` (${Math.round(info.confidence * 100)}%)`;
      }
    } else if (info.offset_ms !== undefined) {
      text += ` (offset: ${info.offset_ms}ms)`;
    }
  }

  syncText.textContent = text;
}

/**
 * Format duration in ms to MM:SS
 */
function formatDuration(ms) {
  if (!ms) return '--:--';
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, '0')}`;
}

/**
 * Start recording (Precision Recording with Whisper)
 */
function startRecording() {
  const title = recordingTitleInput.value.trim() || 'Untitled Recording';
  console.log('[OpenCue Sidebar] startRecording called');

  // First, get current video position from content script
  browser.tabs.query({ active: true, currentWindow: true }).then((tabs) => {
    if (!tabs[0]) {
      addActivityItem('error', 'No streaming tab found');
      return;
    }

    // Get video position before starting recording
    browser.tabs.sendMessage(tabs[0].id, { type: 'getTitle' }).then((response) => {
      const videoStartPositionMs = (response && response.currentPositionMs) || 0;
      const contentId = (response && response.contentId) || '';

      console.log('[OpenCue Sidebar] Video position at recording start:', videoStartPositionMs, 'ms');
      addActivityItem('info', 'Starting at video position: ' + formatDuration(videoStartPositionMs));

      // Update UI
      isRecording = true;
      isPaused = false;
      isProcessing = false;
      precisionRecordingId = 'pending';
      recordingStartTime = Date.now();
      console.log('[OpenCue Sidebar] State set: isRecording=', isRecording, 'isPaused=', isPaused, 'isProcessing=', isProcessing);
      updateRecordingUI();
      startRecordingTimer();

      // Tell content script to show overlay
      browser.tabs.sendMessage(tabs[0].id, {
        type: 'precisionRecordingStarted',
        payload: { success: true, title: title }
      }).catch(() => {
        console.log('[OpenCue Sidebar] Could not notify content script');
      });

      // Use precision recording with video start position
      browser.runtime.sendMessage({
        type: 'startPrecisionRecording',
        payload: {
          title: title,
          content_id: contentId,
          use_virtual_cable: true,
          whisper_model: 'base',
          playback_speed: 1.0,
          video_start_position_ms: videoStartPositionMs  // Critical: offset for cue timestamps
        }
      }).then(() => {
        addActivityItem('record', 'Precision recording started (audio capture)');
      }).catch((err) => {
        isRecording = false;
        updateRecordingUI();
        stopRecordingTimer();
        console.error('Error starting precision recording:', err);
        addActivityItem('error', 'Failed to start recording');
      });

    }).catch((err) => {
      console.log('[OpenCue Sidebar] Could not get video position:', err);
      addActivityItem('error', 'Could not get video position');
    });
  });
}

/**
 * Stop recording (save) - triggers Whisper processing
 */
function stopRecording() {
  console.log('[OpenCue Sidebar] stopRecording() called');

  // Immediately tell content script to stop (pause video, remove overlay)
  browser.tabs.query({ active: true, currentWindow: true }).then((tabs) => {
    if (tabs[0]) {
      browser.tabs.sendMessage(tabs[0].id, {
        type: 'precisionRecordingStopped',
        payload: { success: true }
      }).catch(() => {});
    }
  });

  // Show processing state immediately
  isProcessing = true;
  isRecording = false;
  updateRecordingUI();
  addActivityItem('processing', 'Processing audio with Whisper...');

  // Send stop to backend
  browser.runtime.sendMessage({
    type: 'stopPrecisionRecording',
    payload: { recording_id: precisionRecordingId || 'any' }
  }).then((response) => {
    console.log('[OpenCue Sidebar] stopPrecisionRecording response:', response);
  }).catch((err) => {
    console.error('[OpenCue Sidebar] Error stopping precision recording:', err);
    isProcessing = false;
    isRecording = false;
    precisionRecordingId = null;
    stopRecordingTimer();
    updateRecordingUI();
    addActivityItem('error', 'Failed to stop recording: ' + err.message);
  });
}

/**
 * Abort recording (discard)
 */
function abortRecording() {
  if (!confirm('Abort recording? All captured audio will be discarded.')) {
    return;
  }

  // Clear state immediately
  isRecording = false;
  isPaused = false;
  isProcessing = false;
  lastRecordingState = null;
  stopRecordingTimer();
  updateRecordingUI();

  // Send abort to backend
  browser.runtime.sendMessage({
    type: 'abortPrecisionRecording',
    payload: { recording_id: precisionRecordingId || 'any' }
  }).then(() => {
    precisionRecordingId = null;
    addActivityItem('abort', 'Recording aborted');
  }).catch((err) => {
    console.error('Error aborting recording:', err);
    addActivityItem('error', 'Failed to abort: ' + err.message);
  });
}

/**
 * Handle recording started response
 */
function handleRecordingStarted(payload) {
  console.log('[OpenCue Sidebar] handleRecordingStarted:', payload);
  isRecording = true;
  isProcessing = false;
  recordingStartTime = Date.now();

  // Save precision recording ID if present
  if (payload.recording_id) {
    precisionRecordingId = payload.recording_id;
  }

  // Directly tell content script to show overlay (backup)
  browser.tabs.query({ active: true, currentWindow: true }).then((tabs) => {
    if (tabs[0]) {
      browser.tabs.sendMessage(tabs[0].id, {
        type: 'precisionRecordingStarted',
        payload: payload
      }).catch(() => {});
    }
  });

  // Check if silent mode is active
  if (payload.silent_mode) {
    addActivityItem('info', 'Audio switched to VB-Cable (silent)');
  }

  updateRecordingUI();
  startRecordingTimer();
}

/**
 * Handle recording stopped response (precision recording)
 */
function handleRecordingStopped(payload) {
  console.log('[OpenCue Sidebar] handleRecordingStopped:', payload);
  isRecording = false;
  isProcessing = false;
  precisionRecordingId = null;
  stopRecordingTimer();
  updateRecordingUI();

  // Directly tell content script to remove overlay
  browser.tabs.query({ active: true, currentWindow: true }).then((tabs) => {
    if (tabs[0]) {
      browser.tabs.sendMessage(tabs[0].id, {
        type: 'precisionRecordingStopped',
        payload: payload
      }).catch(() => {
        console.log('[OpenCue Sidebar] Could not send stop to content script');
      });
    }
  });

  if (payload.success && payload.cue_data) {
    // Download the .opencue file
    const cueData = payload.cue_data;
    const filename = sanitizeFilename(cueData.content.title) + '.opencue';
    console.log('[OpenCue Sidebar] Downloading cue file:', filename, 'with', payload.cue_count, 'cues');
    downloadCueFile(cueData, filename);

    const wordCount = payload.word_count || 0;
    addActivityItem('saved', `${payload.cue_count} cues from ${wordCount} words (Whisper)`);

    // Notify about audio restoration
    addActivityItem('info', 'Audio restored to speakers');
  } else if (payload.error) {
    console.error('[OpenCue Sidebar] Recording stop failed:', payload.error);
    addActivityItem('error', `Processing failed: ${payload.error}`);
  }
}

/**
 * Handle precision recording status update
 */
function handlePrecisionRecordingStatus(payload) {
  console.log('[OpenCue Sidebar] handlePrecisionRecordingStatus:', payload);
  if (payload.active) {
    isRecording = true;
    isProcessing = false;
    isPaused = false;
    precisionRecordingId = payload.recording_id;

    // Switch to recording mode and show recording section
    currentMode = 'recording';
    cueSection.style.display = 'none';
    recordingSection.style.display = 'block';
    updateModeUI();

    // Restore title if available
    if (payload.title) {
      recordingTitleInput.value = payload.title;
    }

    if (payload.chunks_captured) {
      recFpCount.textContent = `${payload.chunks_captured} chunks`;
    }
    if (payload.duration_ms) {
      // Restore timer from duration
      recordingStartTime = Date.now() - payload.duration_ms;
      startRecordingTimer();
    }
    updateRecordingUI();
  } else {
    // No active recording - reset all state
    isRecording = false;
    isProcessing = false;
    isPaused = false;
    precisionRecordingId = null;
    stopRecordingTimer();
    updateRecordingUI();
  }
}

/**
 * Handle recording aborted response
 */
function handleRecordingAborted(payload) {
  console.log('[OpenCue Sidebar] handleRecordingAborted:', payload);
  isRecording = false;
  isProcessing = false;
  precisionRecordingId = null;
  stopRecordingTimer();
  updateRecordingUI();

  // Directly tell content script to remove overlay
  browser.tabs.query({ active: true, currentWindow: true }).then((tabs) => {
    if (tabs[0]) {
      browser.tabs.sendMessage(tabs[0].id, {
        type: 'precisionRecordingAborted',
        payload: payload
      }).catch(() => {});
    }
  });

  addActivityItem('abort', 'Recording aborted, audio restored');
}

/**
 * Handle precision requirements check response
 */
function handlePrecisionRequirements(payload) {
  console.log('[OpenCue Sidebar] handlePrecisionRequirements:', payload);
  if (!payload.ready) {
    // Show what's missing
    let missing = [];
    if (!payload.virtual_cable?.installed) {
      missing.push('VB-Cable not installed');
    }
    if (!payload.whisper?.available) {
      missing.push('Whisper not available');
    }
    if (missing.length > 0) {
      addActivityItem('error', 'Missing: ' + missing.join(', '));
    }
  }
}

/**
 * Update recording UI
 *
 * Uses separate divs for each state - no complex show/hide logic
 */
function updateRecordingUI() {
  console.log('[OpenCue Sidebar] updateRecordingUI: isRecording=', isRecording, 'isProcessing=', isProcessing);

  const controlsIdle = document.getElementById('controls-idle');
  const controlsRecording = document.getElementById('controls-recording');
  const controlsProcessing = document.getElementById('controls-processing');

  if (isProcessing) {
    // Whisper is processing
    controlsIdle.style.display = 'none';
    controlsRecording.style.display = 'none';
    controlsProcessing.style.display = 'flex';
    recordingStatus.style.display = 'flex';
    recordingTitleInput.disabled = true;
  } else if (isRecording) {
    // Recording in progress - show Stop and Abort
    controlsIdle.style.display = 'none';
    controlsRecording.style.display = 'flex';
    controlsProcessing.style.display = 'none';
    recordingStatus.style.display = 'flex';
    recordingTitleInput.disabled = true;
  } else {
    // Idle - show Start only
    controlsIdle.style.display = 'flex';
    controlsRecording.style.display = 'none';
    controlsProcessing.style.display = 'none';
    recordingStatus.style.display = 'none';
    recordingTitleInput.disabled = false;
  }

  // Always hide paused status (not using pause feature)
  if (pausedStatus) pausedStatus.style.display = 'none';
}

/**
 * Start recording timer
 */
function startRecordingTimer() {
  if (recordingTimer) return;  // Don't start multiple timers
  recordingTimer = setInterval(() => {
    if (recordingStartTime) {
      const elapsed = Date.now() - recordingStartTime;
      recElapsed.textContent = formatDuration(elapsed);
    }
  }, 1000);
}

/**
 * Stop recording timer
 */
function stopRecordingTimer() {
  if (recordingTimer) {
    clearInterval(recordingTimer);
    recordingTimer = null;
  }
}

/**
 * Update recording cue count
 */
function updateRecordingCueCount(count) {
  recCueCount.textContent = `${count} cue${count !== 1 ? 's' : ''}`;
}

/**
 * Update recording fingerprint count
 */
function updateRecordingFpCount(count) {
  if (recFpCount) {
    recFpCount.textContent = `${count} fp`;
    recFpCount.title = `${count} audio fingerprint${count !== 1 ? 's' : ''} captured for cross-platform sync`;
  }
}

/**
 * Download cue file
 */
function downloadCueFile(data, filename) {
  const json = JSON.stringify(data, null, 2);
  const blob = new Blob([json], { type: 'application/json' });
  const url = URL.createObjectURL(blob);

  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);

  console.log('Downloaded:', filename);
}

/**
 * Sanitize filename
 */
function sanitizeFilename(name) {
  return name
    .replace(/[<>:"/\\|?*]/g, '')
    .replace(/\s+/g, '_')
    .substring(0, 100);
}

/**
 * Search for cue files by title
 */
function searchCueFiles(query) {
  browser.runtime.sendMessage({
    type: 'searchCueFiles',
    payload: { query: query }
  }).catch((err) => {
    console.error('Error searching cue files:', err);
  });
}

/**
 * Handle search results from backend
 */
function handleSearchResults(payload) {
  const query = payload.query;
  const files = payload.files || [];

  // If this was an auto-search for current content
  if (detectedTitle && query.toLowerCase() === detectedTitle.toLowerCase()) {
    matchedFiles = files;
    renderMatchedFiles();
  } else {
    // Manual search - show in main list
    cueFiles = files;
    renderCueFiles();
  }
}

/**
 * Render matched files for current content
 */
function renderMatchedFiles() {
  if (!matchedCueFiles) return;

  if (matchedFiles.length === 0) {
    currentContentMatch.style.display = detectedTitle ? 'block' : 'none';
    matchedCueFiles.innerHTML = '<p class="empty-state">No matching cue files found</p>';
    return;
  }

  currentContentMatch.style.display = 'block';
  currentContentTitle.textContent = `Matches for: ${detectedTitle}`;

  matchedCueFiles.innerHTML = '';
  matchedFiles.forEach((file) => {
    const item = document.createElement('div');
    item.className = 'cue-file-item matched' + (file.id === selectedCueFile ? ' selected' : '');
    item.dataset.id = file.id;

    const duration = formatDuration(file.duration_ms);
    const badge = file.has_fingerprints
      ? '<span class="cue-file-badge has-fp">Audio Sync</span>'
      : '<span class="cue-file-badge">Timestamps</span>';

    item.innerHTML = `
      <div class="cue-file-info">
        <div class="cue-file-title">${file.title}</div>
        <div class="cue-file-meta">${file.cue_count} cues - ${duration}</div>
      </div>
      ${badge}
    `;

    item.addEventListener('click', () => selectCueFile(file.id));
    matchedCueFiles.appendChild(item);
  });
}

/**
 * Auto-search for current content when title is detected
 */
function autoSearchForContent(title) {
  if (!title || title === 'Unknown Title') return;

  detectedTitle = title;
  if (currentContentTitle) {
    currentContentTitle.textContent = `Searching for: ${title}...`;
    currentContentMatch.style.display = 'block';
  }

  // Search for matching cue files
  searchCueFiles(title);
}

// Event listeners
connectBtn.addEventListener('click', connect);
disconnectBtn.addEventListener('click', disconnect);

// Mode button listeners
modeButtons.forEach((btn) => {
  btn.addEventListener('click', () => {
    // Skip disabled buttons (e.g., real-time mode)
    if (btn.disabled || btn.classList.contains('disabled')) {
      return;
    }
    setMode(btn.dataset.mode);
  });
});

// Recording button listeners
startRecordingBtn.addEventListener('click', startRecording);
stopRecordingBtn.addEventListener('click', stopRecording);
abortRecordingBtn.addEventListener('click', abortRecording);
fetchTitleBtn.addEventListener('click', fetchContentTitle);

// Auto-stop checkbox listener
if (autoStopCheckbox) {
  autoStopCheckbox.addEventListener('change', () => {
    autoStopEnabled = autoStopCheckbox.checked;
    console.log('[OpenCue Sidebar] Auto-stop:', autoStopEnabled ? 'enabled' : 'disabled');
  });
}

// Cue search listeners
if (cueSearchBtn) {
  cueSearchBtn.addEventListener('click', () => {
    const query = cueSearchInput.value.trim();
    if (query) {
      searchCueFiles(query);
    } else {
      loadCueFiles(); // Show all if empty
    }
  });
}
if (cueSearchInput) {
  cueSearchInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
      const query = cueSearchInput.value.trim();
      if (query) {
        searchCueFiles(query);
      } else {
        loadCueFiles();
      }
    }
  });
}

/**
 * Fetch content title from active streaming tab
 */
function fetchContentTitle() {
  // Show loading state
  if (fetchTitleBtn) {
    fetchTitleBtn.textContent = '...';
    fetchTitleBtn.disabled = true;
  }

  // Query for all supported streaming service tabs
  const streamingUrls = [
    '*://*.netflix.com/*',
    '*://*.disneyplus.com/*',
    '*://*.hulu.com/*',
    '*://*.amazon.com/*',
    '*://*.primevideo.com/*',
    '*://*.max.com/*',
    '*://*.hbomax.com/*',
    '*://*.peacocktv.com/*',
    '*://*.paramountplus.com/*',
    '*://*.apple.com/*',
    '*://*.tv.apple.com/*',
    '*://*.crunchyroll.com/*',
    '*://*.youtube.com/*',
    '*://*.vudu.com/*',
    '*://*.tubitv.com/*',
    '*://*.pluto.tv/*'
  ];

  const resetButton = () => {
    if (fetchTitleBtn) {
      fetchTitleBtn.textContent = 'Get Title';
      fetchTitleBtn.disabled = false;
    }
  };

  browser.tabs.query({
    active: true,
    currentWindow: true,
    url: streamingUrls
  }).then((tabs) => {
    if (tabs.length > 0) {
      // Send message to content script to get title
      browser.tabs.sendMessage(tabs[0].id, { type: 'getTitle' }).then((response) => {
        resetButton();
        if (response && response.title && response.title !== 'Unknown Title') {
          recordingTitleInput.value = response.title;
          recordingTitleInput.placeholder = response.title;
          console.log('[OpenCue Sidebar] Fetched title:', response.title);

          // Store and display duration
          if (response.durationMs && response.durationMs > 0) {
            videoDurationMs = response.durationMs;
            const durationStr = formatDuration(videoDurationMs);
            if (durationDisplay) {
              durationDisplay.textContent = `Duration: ${durationStr}`;
            }
            addActivityItem('info', `${response.title} (${durationStr})`);
            console.log('[OpenCue Sidebar] Duration:', durationStr);
          } else {
            if (durationDisplay) {
              durationDisplay.textContent = '';
            }
            addActivityItem('info', `Title: ${response.title}`);
          }

          // Auto-search for matching cue files
          autoSearchForContent(response.title);
        } else {
          addActivityItem('error', 'Could not detect title');
        }
      }).catch((err) => {
        resetButton();
        console.log('[OpenCue Sidebar] Could not get title from tab:', err.message);
        addActivityItem('error', 'No response from page');
      });
    } else {
      resetButton();
      addActivityItem('error', 'No streaming tab found');
    }
  }).catch((err) => {
    resetButton();
    console.log('[OpenCue Sidebar] Error querying tabs:', err);
    addActivityItem('error', 'Error querying tabs');
  });
}

/**
 * Check if recording is in progress when sidebar opens
 */
function checkRecordingStatus() {
  browser.runtime.sendMessage({
    type: 'getPrecisionRecordingStatus',
    payload: {}
  }).catch((err) => {
    console.log('[OpenCue Sidebar] Could not check status:', err.message);
  });
}

// Initialize
getConnectionState();
setMode('recording');  // Default to recording mode (real-time disabled)
fetchContentTitle();
checkRecordingStatus();
