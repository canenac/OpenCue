/**
 * OpenCue Dashboard - Frontend Application
 */

// API base URL
const API_BASE = '';

// Elements
const statusBadge = document.getElementById('status-badge');
const wsConnectionsEl = document.getElementById('ws-connections');
const eventsCountEl = document.getElementById('events-count');
const eventsListEl = document.getElementById('events-list');
const refreshBtn = document.getElementById('refresh-btn');
const clearBtn = document.getElementById('clear-btn');

// State
let events = [];
let isConnected = false;

/**
 * Fetch backend status
 */
async function fetchStatus() {
  try {
    const response = await fetch(`${API_BASE}/api/status`);
    if (!response.ok) throw new Error('Backend unreachable');

    const data = await response.json();
    isConnected = true;
    updateStatusBadge(true);
    wsConnectionsEl.textContent = data.websocket_connections || 0;
  } catch (error) {
    console.error('Failed to fetch status:', error);
    isConnected = false;
    updateStatusBadge(false);
    wsConnectionsEl.textContent = '-';
  }
}

/**
 * Fetch recent events
 */
async function fetchEvents() {
  try {
    const response = await fetch(`${API_BASE}/api/recent-events`);
    if (!response.ok) throw new Error('Failed to fetch events');

    const data = await response.json();
    events = data.events || [];
    eventsCountEl.textContent = events.length;
    renderEvents();
  } catch (error) {
    console.error('Failed to fetch events:', error);
    eventsCountEl.textContent = '-';
  }
}

/**
 * Update status badge
 */
function updateStatusBadge(connected) {
  if (connected) {
    statusBadge.className = 'status-badge connected';
    statusBadge.querySelector('.status-text').textContent = 'Connected';
  } else {
    statusBadge.className = 'status-badge disconnected';
    statusBadge.querySelector('.status-text').textContent = 'Disconnected';
  }
}

/**
 * Render events list
 */
function renderEvents() {
  if (events.length === 0) {
    eventsListEl.innerHTML = '<p class="empty-state">No events yet. Start watching something on Netflix with the extension active.</p>';
    return;
  }

  eventsListEl.innerHTML = events.map(event => {
    const action = event.action || 'unknown';
    const category = event.category || 'unknown';
    const detected = event.detected || '';
    const timestamp = event.timestamp ? new Date(event.timestamp).toLocaleTimeString() : '';

    return `
      <div class="event-item">
        <span class="event-action ${action}">${action}</span>
        <div class="event-details">
          <div class="event-category">${formatCategory(category)}</div>
          <div class="event-detected">Detected: ${detected}</div>
        </div>
        <span class="event-time">${timestamp}</span>
      </div>
    `;
  }).join('');
}

/**
 * Format category for display
 */
function formatCategory(category) {
  return category
    .split('.')
    .map(part => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' > ');
}

/**
 * Clear events display
 */
function clearEvents() {
  events = [];
  eventsCountEl.textContent = '0';
  renderEvents();
}

/**
 * Refresh all data
 */
async function refresh() {
  await Promise.all([fetchStatus(), fetchEvents()]);
}

// Event listeners
refreshBtn.addEventListener('click', refresh);
clearBtn.addEventListener('click', clearEvents);

// Initial load
refresh();

// Auto-refresh every 5 seconds
setInterval(refresh, 5000);

console.log('[OpenCue] Dashboard loaded');
