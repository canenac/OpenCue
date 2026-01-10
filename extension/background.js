/**
 * OpenCue - Background Script
 *
 * Manages WebSocket connection to the local backend and relays messages
 * between content scripts and the backend.
 */

const BACKEND_WS_URL = 'ws://localhost:8765';
let websocket = null;
let connectionState = 'disconnected';
let reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 999;
const RECONNECT_DELAY_MS = 3000;

/**
 * Initialize WebSocket connection to backend
 */
function connectToBackend() {
    if (websocket && websocket.readyState === WebSocket.OPEN) {
        console.log('[OpenCue] Already connected to backend');
        return;
    }

    console.log('[OpenCue] Connecting to backend:', BACKEND_WS_URL);
    connectionState = 'connecting';
    broadcastConnectionState();

    try {
        websocket = new WebSocket(BACKEND_WS_URL);

        websocket.onopen = () => {
            console.log('[OpenCue] Connected to backend');
            connectionState = 'connected';
            reconnectAttempts = 0;
            broadcastConnectionState();
        };

        websocket.onclose = (event) => {
            console.log('[OpenCue] Disconnected from backend:', event.code, event.reason);
            connectionState = 'disconnected';
            websocket = null;
            broadcastConnectionState();

            // Attempt reconnection
            if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
                reconnectAttempts++;
                console.log(`[OpenCue] Reconnecting in ${RECONNECT_DELAY_MS}ms (attempt ${reconnectAttempts})`);
                setTimeout(connectToBackend, RECONNECT_DELAY_MS);
            }
        };

        websocket.onerror = (error) => {
            console.error('[OpenCue] WebSocket error:', error);
            connectionState = 'error';
            broadcastConnectionState();
        };

        websocket.onmessage = (event) => {
            handleBackendMessage(event.data);
        };
    } catch (error) {
        console.error('[OpenCue] Failed to create WebSocket:', error);
        connectionState = 'error';
        broadcastConnectionState();
    }
}

/**
 * Handle messages from the backend
 */
function handleBackendMessage(data) {
    try {
        const message = JSON.parse(data);
        console.log('[OpenCue] Received from backend:', message.type);

        // Messages to forward to content scripts
        const forwardTypes = ['overlay', 'cue', 'cueEnd', 'syncState', 'modeSet', 'cueFileLoaded', 'sessionInfo', 'recordingStarted', 'recordingStopped', 'recordingStatus', 'recordingAborted', 'recordingPaused', 'recordingResumed', 'precisionRecordingStarted', 'precisionRecordingStopped', 'precisionRecordingStatus', 'precisionRecordingAborted'];

        // All supported streaming service URLs
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

        if (forwardTypes.includes(message.type)) {
            // Forward to all supported streaming tabs
            browser.tabs.query({ url: streamingUrls }).then((tabs) => {
                tabs.forEach((tab) => {
                    browser.tabs.sendMessage(tab.id, message).catch((err) => {
                        // Tab might not have content script loaded yet
                        console.log('[OpenCue] Could not send to tab:', tab.id);
                    });
                });
            });
        }

        // Also forward certain messages to popup/sidebar
        const popupTypes = ['cueFileList', 'cueFileSearchResults', 'syncState', 'cueFileLoaded', 'recordingStarted', 'recordingStopped', 'recordingStatus', 'recordingAborted', 'recordingPaused', 'recordingResumed', 'precisionRecordingStarted', 'precisionRecordingStopped', 'precisionRecordingStatus', 'precisionRecordingAborted', 'precisionRequirements'];
        if (popupTypes.includes(message.type)) {
            browser.runtime.sendMessage(message).catch(() => {
                // Popup/sidebar might not be open
            });
        }
    } catch (error) {
        console.error('[OpenCue] Error parsing backend message:', error);
    }
}

/**
 * Send message to backend
 */
function sendToBackend(message) {
    if (websocket && websocket.readyState === WebSocket.OPEN) {
        websocket.send(JSON.stringify(message));
        return true;
    } else {
        console.warn('[OpenCue] Cannot send - not connected to backend');
        return false;
    }
}

/**
 * Broadcast connection state to popup/sidebar and content scripts
 */
function broadcastConnectionState() {
    const stateMessage = {
        type: 'connectionState',
        payload: { state: connectionState }
    };

    // Send to popup/sidebar if open
    browser.runtime.sendMessage(stateMessage).catch(() => {
        // Popup/sidebar might not be open
    });

    // All supported streaming service URLs
    const streamingUrls = [
        '*://*.netflix.com/*', '*://*.disneyplus.com/*', '*://*.hulu.com/*',
        '*://*.amazon.com/*', '*://*.primevideo.com/*', '*://*.max.com/*',
        '*://*.hbomax.com/*', '*://*.peacocktv.com/*', '*://*.paramountplus.com/*',
        '*://*.apple.com/*', '*://*.tv.apple.com/*', '*://*.crunchyroll.com/*',
        '*://*.youtube.com/*', '*://*.vudu.com/*', '*://*.tubitv.com/*', '*://*.pluto.tv/*'
    ];

    // Send to all streaming tabs
    browser.tabs.query({ url: streamingUrls }).then((tabs) => {
        tabs.forEach((tab) => {
            browser.tabs.sendMessage(tab.id, stateMessage).catch(() => {
                // Tab might not have content script
            });
        });
    });
}

/**
 * Handle messages from content scripts and popup/sidebar
 */
browser.runtime.onMessage.addListener((message, sender, sendResponse) => {
    console.log('[OpenCue] Received message:', message.type);

    switch (message.type) {
        case 'getConnectionState':
            sendResponse({ state: connectionState });
            break;

        case 'connect':
            reconnectAttempts = 0;
            connectToBackend();
            sendResponse({ success: true });
            break;

        case 'disconnect':
            if (websocket) {
                websocket.close();
                websocket = null;
            }
            connectionState = 'disconnected';
            broadcastConnectionState();
            sendResponse({ success: true });
            break;

        case 'subtitle':
        case 'playback':
        case 'position':
        case 'setMode':
        case 'loadCueFile':
        case 'listCueFiles':
        case 'searchCueFiles':
        case 'getSessionInfo':
        case 'startRecording':
        case 'stopRecording':
        case 'getRecordingStatus':
        case 'abortRecording':
        case 'pauseRecording':
        case 'resumeRecording':
        case 'startPrecisionRecording':
        case 'stopPrecisionRecording':
        case 'abortPrecisionRecording':
        case 'getPrecisionRecordingStatus':
        case 'checkPrecisionRequirements':
            // Forward to backend
            sendResponse({ success: sendToBackend(message) });
            break;

        case 'videoEnded':
            // Forward video ended event to sidebar/popup for auto-stop recording
            browser.runtime.sendMessage(message).catch(() => {});
            sendResponse({ success: true });
            break;

        default:
            console.log('[OpenCue] Unknown message type:', message.type);
            sendResponse({ success: false, error: 'Unknown message type' });
    }

    return true; // Keep message channel open for async response
});

/**
 * Handle browser action (toolbar button) click - toggle sidebar
 */
browser.browserAction.onClicked.addListener(() => {
    browser.sidebarAction.toggle();
});

// Initialize connection on startup
connectToBackend();

console.log('[OpenCue] Background script loaded');
