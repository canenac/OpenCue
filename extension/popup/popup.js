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

// State
let currentState = 'disconnected';
const activityItems = [];

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

    case 'overlay':
      // Log overlay activity
      const action = message.payload.action;
      const category = message.payload.category || 'unknown';
      addActivityItem(action, category);
      break;
  }

  sendResponse({ received: true });
  return true;
});

// Event listeners
connectBtn.addEventListener('click', connect);
disconnectBtn.addEventListener('click', disconnect);

// Initialize
getConnectionState();
