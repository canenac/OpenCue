/**
 * OpenCue - Content Script
 *
 * Injected into Netflix pages to:
 * 1. Detect video playback
 * 2. Extract subtitle/caption data
 * 3. Apply audio muting based on overlay commands
 * 4. (Future) Apply visual blur overlays
 */

console.log('[OpenCue] Content script loaded on Netflix');

// State
let videoElement = null;
let isActive = true;
let pendingOverlays = [];
let subtitleObserver = null;

/**
 * Find the Netflix video element
 */
function findVideoElement() {
  const video = document.querySelector('video');
  if (video && video !== videoElement) {
    videoElement = video;
    console.log('[OpenCue] Video element found');
    setupVideoListeners();
    setupSubtitleObserver();
    return true;
  }
  return !!videoElement;
}

/**
 * Set up listeners on the video element
 */
function setupVideoListeners() {
  if (!videoElement) return;

  videoElement.addEventListener('play', () => {
    console.log('[OpenCue] Video playing');
    sendPlaybackStatus('playing');
  });

  videoElement.addEventListener('pause', () => {
    console.log('[OpenCue] Video paused');
    sendPlaybackStatus('paused');
  });

  videoElement.addEventListener('timeupdate', () => {
    checkPendingOverlays();
  });

  videoElement.addEventListener('seeked', () => {
    console.log('[OpenCue] Video seeked to:', videoElement.currentTime);
  });
}

/**
 * Set up MutationObserver to watch for subtitle changes
 */
function setupSubtitleObserver() {
  // Netflix uses a specific class for subtitle containers
  // This may need adjustment as Netflix updates their UI
  const subtitleSelectors = [
    '.player-timedtext',
    '.player-timedtext-text-container',
    '[data-uia="player-timedtext"]'
  ];

  // Disconnect existing observer
  if (subtitleObserver) {
    subtitleObserver.disconnect();
  }

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
  // Look for Netflix subtitle elements
  const subtitleElements = node.querySelectorAll
    ? node.querySelectorAll('.player-timedtext-text-container span, [data-uia="player-timedtext"] span')
    : [];

  for (const el of subtitleElements) {
    const text = el.textContent?.trim();
    if (text) {
      handleSubtitleText(text);
    }
  }

  // Also check the node itself
  if (node.classList?.contains('player-timedtext-text-container') ||
      node.getAttribute?.('data-uia') === 'player-timedtext') {
    const text = node.textContent?.trim();
    if (text) {
      handleSubtitleText(text);
    }
  }
}

/**
 * Handle extracted subtitle text
 */
let lastSubtitleText = '';
let lastSubtitleTime = 0;

function handleSubtitleText(text) {
  // Avoid duplicate sends
  if (text === lastSubtitleText && Date.now() - lastSubtitleTime < 500) {
    return;
  }

  lastSubtitleText = text;
  lastSubtitleTime = Date.now();

  const currentTimeMs = videoElement ? Math.floor(videoElement.currentTime * 1000) : 0;

  console.log('[OpenCue] Subtitle:', text.substring(0, 50) + (text.length > 50 ? '...' : ''));

  // Send to backend for analysis
  sendSubtitle(text, currentTimeMs);
}

/**
 * Send subtitle to backend for analysis
 */
function sendSubtitle(text, startMs) {
  const contentId = getContentId();
  const endMs = startMs + 3000; // Estimate 3 second subtitle duration

  browser.runtime.sendMessage({
    type: 'subtitle',
    payload: {
      text: text,
      start_ms: startMs,
      end_ms: endMs,
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
 * Get content ID from Netflix URL
 */
function getContentId() {
  const match = window.location.pathname.match(/\/watch\/(\d+)/);
  return match ? `netflix:${match[1]}` : 'netflix:unknown';
}

/**
 * Handle overlay commands from backend
 */
function handleOverlayCommand(command) {
  console.log('[OpenCue] Overlay command:', command.action, command.start_ms, '-', command.end_ms);

  // Add to pending overlays
  pendingOverlays.push({
    ...command,
    applied: false
  });

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

  if (shouldMute && !videoElement.muted) {
    videoElement.muted = true;
    console.log('[OpenCue] Audio muted');
  } else if (!shouldMute && videoElement.muted) {
    videoElement.muted = false;
    console.log('[OpenCue] Audio unmuted');
  }
}

/**
 * Handle messages from background script
 */
browser.runtime.onMessage.addListener((message, sender, sendResponse) => {
  switch (message.type) {
    case 'overlay':
      handleOverlayCommand(message.payload);
      sendResponse({ success: true });
      break;

    case 'connectionState':
      console.log('[OpenCue] Backend connection:', message.payload.state);
      sendResponse({ success: true });
      break;

    case 'setActive':
      isActive = message.payload.active;
      console.log('[OpenCue] Active state:', isActive);
      if (!isActive) {
        // Remove any active overlays
        muteAudio(false);
      }
      sendResponse({ success: true });
      break;

    default:
      sendResponse({ success: false, error: 'Unknown message type' });
  }

  return true;
});

/**
 * Periodically check for video element (Netflix loads dynamically)
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

// Initialize
initVideoDetection();
