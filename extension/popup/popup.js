/**
 * OpenCue - Popup Script
 *
 * Controls for the browser action popup.
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

// Recording elements
const recordingSection = document.getElementById('recording-section');
const recordingTitleInput = document.getElementById('recording-title');
const startRecordingBtn = document.getElementById('start-recording');
const resumeRecordingBtn = document.getElementById('resume-recording');
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
let currentMode = 'realtime';
let selectedCueFile = null;
let cueFiles = [];
let isRecording = false;
let isPaused = false;
let recordingStartTime = null;
let recordingTimer = null;
let lastRecordingState = null;  // For resume functionality
const activityItems = [];

// Mode descriptions
const modeDescriptions = {
  realtime: 'Detect profanity from live subtitles',
  cue_file: 'Use pre-analyzed .opencue files with audio sync',
  recording: 'Record cues while watching, then save for later'
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

  // Keep only last 10 items
  while (activityLog.children.length > 10) {
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
      handleRecordingStarted(message.payload);
      break;

    case 'recordingStopped':
      handleRecordingStopped(message.payload);
      break;

    case 'recordingStatus':
      if (message.payload.recording) {
        // Restore recording state if popup was reopened during recording
        if (!isRecording) {
          isRecording = true;
          currentMode = 'recording';
          updateModeUI();
          // Show recording section
          cueSection.style.display = 'none';
          recordingSection.style.display = 'block';
          startRecordingTimer();
          recordingTitleInput.value = message.payload.title || '';
        }
        updateRecordingCueCount(message.payload.cue_count);
        updateRecordingFpCount(message.payload.fingerprint_count || 0);
        updateRecordingUI();
      } else if (isRecording) {
        // Recording stopped elsewhere
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
        <div class="cue-file-meta">${file.cue_count} cues • ${duration}</div>
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
  syncIndicator.className = 'sync-indicator ' + state;

  const stateTexts = {
    idle: 'Not synced',
    syncing: 'Syncing...',
    synced: 'Synced',
    lost: 'Lost sync',
    error: 'Error'
  };

  let text = stateTexts[state] || state;
  if (state === 'synced' && info.offset_ms !== undefined) {
    text += ` (offset: ${info.offset_ms}ms)`;
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
 * Start recording
 */
function startRecording() {
  const title = recordingTitleInput.value.trim() || 'Untitled Recording';

  browser.runtime.sendMessage({
    type: 'startRecording',
    payload: {
      title: title,
      content_id: '' // Will be filled from playback
    }
  }).then(() => {
    isRecording = true;
    recordingStartTime = Date.now();
    updateRecordingUI();
    startRecordingTimer();
    addActivityItem('record', 'Recording started');
  }).catch((err) => {
    console.error('Error starting recording:', err);
  });
}

/**
 * Stop recording (save)
 */
function stopRecording() {
  browser.runtime.sendMessage({
    type: 'stopRecording',
    payload: { save: true }
  }).catch((err) => {
    console.error('Error stopping recording:', err);
  });
}

/**
 * Abort recording (discard)
 */
function abortRecording() {
  if (!confirm('Abort recording? All captured cues will be lost.')) {
    return;
  }

  browser.runtime.sendMessage({
    type: 'abortRecording',
    payload: {}
  }).then(() => {
    isRecording = false;
    isPaused = false;
    lastRecordingState = null;
    stopRecordingTimer();
    updateRecordingUI();
    addActivityItem('abort', 'Recording aborted');
  }).catch((err) => {
    console.error('Error aborting recording:', err);
  });
}

/**
 * Pause recording (for resume later)
 */
function pauseRecording() {
  browser.runtime.sendMessage({
    type: 'pauseRecording',
    payload: {}
  }).then((response) => {
    if (response && response.success) {
      isPaused = true;
      lastRecordingState = response.state;
      stopRecordingTimer();
      updateRecordingUI();
      addActivityItem('pause', `Paused at ${formatDuration(response.state.position_ms)}`);
    }
  }).catch((err) => {
    console.error('Error pausing recording:', err);
  });
}

/**
 * Resume recording from paused state
 */
function resumeRecording() {
  const resumePosition = lastRecordingState ? lastRecordingState.position_ms : 0;

  browser.runtime.sendMessage({
    type: 'resumeRecording',
    payload: {
      position_ms: resumePosition
    }
  }).then(() => {
    isRecording = true;
    isPaused = false;
    recordingStartTime = Date.now() - (lastRecordingState ? lastRecordingState.elapsed_ms : 0);
    updateRecordingUI();
    startRecordingTimer();
    addActivityItem('resume', `Resumed from ${formatDuration(resumePosition)}`);
  }).catch((err) => {
    console.error('Error resuming recording:', err);
  });
}

/**
 * Handle recording started response
 */
function handleRecordingStarted(payload) {
  isRecording = true;
  recordingStartTime = Date.now();
  updateRecordingUI();
  startRecordingTimer();
}

/**
 * Handle recording stopped response
 */
function handleRecordingStopped(payload) {
  isRecording = false;
  stopRecordingTimer();
  updateRecordingUI();

  if (payload.success && payload.cue_data) {
    // Download the .opencue file
    const cueData = payload.cue_data;
    const filename = sanitizeFilename(cueData.content.title) + '.opencue';
    downloadCueFile(cueData, filename);

    const fpCount = payload.fingerprint_count || 0;
    const fpText = fpCount > 0 ? `, ${fpCount} fingerprints` : '';
    addActivityItem('saved', `${payload.cue_count} cues${fpText} saved`);
  }
}

/**
 * Update recording UI
 */
function updateRecordingUI() {
  if (isRecording && !isPaused) {
    // Actively recording
    startRecordingBtn.disabled = true;
    startRecordingBtn.style.display = 'none';
    resumeRecordingBtn.style.display = 'none';
    stopRecordingBtn.disabled = false;
    abortRecordingBtn.disabled = false;
    recordingTitleInput.disabled = true;
    recordingStatus.style.display = 'flex';
    pausedStatus.style.display = 'none';
  } else if (isPaused && lastRecordingState) {
    // Paused - can resume
    startRecordingBtn.style.display = 'none';
    resumeRecordingBtn.style.display = 'inline-block';
    resumeRecordingBtn.disabled = false;
    stopRecordingBtn.disabled = false;
    abortRecordingBtn.disabled = false;
    recordingTitleInput.disabled = true;
    recordingStatus.style.display = 'none';
    pausedStatus.style.display = 'flex';
    pausedPosition.textContent = formatDuration(lastRecordingState.position_ms);
    pausedCues.textContent = lastRecordingState.cue_count;
  } else {
    // Not recording
    startRecordingBtn.disabled = false;
    startRecordingBtn.style.display = 'inline-block';
    resumeRecordingBtn.style.display = 'none';
    stopRecordingBtn.disabled = true;
    abortRecordingBtn.disabled = true;
    recordingTitleInput.disabled = false;
    recordingStatus.style.display = 'none';
    pausedStatus.style.display = 'none';
  }
}

/**
 * Start recording timer
 */
function startRecordingTimer() {
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

// Event listeners
connectBtn.addEventListener('click', connect);
disconnectBtn.addEventListener('click', disconnect);

// Mode button listeners
modeButtons.forEach((btn) => {
  btn.addEventListener('click', () => {
    setMode(btn.dataset.mode);
  });
});

// Recording button listeners
startRecordingBtn.addEventListener('click', startRecording);
resumeRecordingBtn.addEventListener('click', resumeRecording);
stopRecordingBtn.addEventListener('click', stopRecording);
abortRecordingBtn.addEventListener('click', abortRecording);

/**
 * Fetch content title from active streaming tab
 */
function fetchContentTitle() {
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

  browser.tabs.query({
    active: true,
    currentWindow: true,
    url: streamingUrls
  }).then((tabs) => {
    if (tabs.length > 0) {
      // Send message to content script to get title
      browser.tabs.sendMessage(tabs[0].id, { type: 'getTitle' }).then((response) => {
        if (response && response.title && response.title !== 'Unknown Title') {
          recordingTitleInput.value = response.title;
          recordingTitleInput.placeholder = response.title;
          console.log('[OpenCue] Auto-detected title:', response.title);
        }
      }).catch((err) => {
        console.log('[OpenCue] Could not get title from tab:', err.message);
      });
    }
  }).catch((err) => {
    console.log('[OpenCue] Error querying tabs:', err);
  });
}

/**
 * Check if recording is in progress when popup opens
 */
function checkRecordingStatus() {
  browser.runtime.sendMessage({
    type: 'getRecordingStatus',
    payload: {}
  }).then((response) => {
    if (response && response.success !== false) {
      // Backend will respond with recordingStatus message
      console.log('[OpenCue] Requested recording status');
    }
  }).catch((err) => {
    console.log('[OpenCue] Could not get recording status:', err.message);
  });
}

// Initialize
getConnectionState();
updateModeUI();
fetchContentTitle();
checkRecordingStatus();
