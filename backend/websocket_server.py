"""
OpenCue - WebSocket Server

Handles real-time communication with browser extensions.
Supports both real-time detection and cue-file sync modes.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Set

import websockets
from websockets.server import WebSocketServerProtocol

from overlay_engine import process_subtitle, record_event
from sync_session import get_session_manager, SessionMode

# Server configuration
WS_HOST = "localhost"
WS_PORT = 8765

# Active connections
connections: Set[WebSocketServerProtocol] = set()

# Server instance
server = None


async def handle_connection(websocket: WebSocketServerProtocol):
    """Handle a WebSocket connection from browser extension"""
    connections.add(websocket)
    client_id = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
    print(f"[OpenCue] Extension connected: {client_id}")

    # Create session
    session_manager = get_session_manager()
    session = session_manager.create_session(websocket)

    try:
        async for message in websocket:
            await handle_message(websocket, session, message)
    except websockets.exceptions.ConnectionClosed as e:
        print(f"[OpenCue] Connection closed: {client_id} ({e.code})")
    finally:
        connections.discard(websocket)
        session_manager.remove_session(session)
        print(f"[OpenCue] Extension disconnected: {client_id}")


async def handle_message(websocket: WebSocketServerProtocol, session, raw_message: str):
    """Handle incoming message from extension"""
    try:
        message = json.loads(raw_message)
        msg_type = message.get("type")
        payload = message.get("payload", {})
        print(f"[OpenCue] Received: {msg_type}")

        if msg_type == "subtitle":
            # Real-time subtitle processing (including recording mode)
            if session.mode in [SessionMode.REALTIME, SessionMode.HYBRID, SessionMode.RECORDING]:
                text = payload.get("text", "")
                print(f"[OpenCue] Subtitle: {text[:80]}{'...' if len(text) > 80 else ''}")

                # Process subtitle and check for overlay triggers
                overlay_commands = await process_subtitle(
                    text=payload.get("text", ""),
                    start_ms=payload.get("start_ms", 0),
                    end_ms=payload.get("end_ms", 0),
                    content_id=payload.get("content_id", "")
                )

                # Send overlay commands back to extension (and record if in recording mode)
                for command in overlay_commands:
                    await send_overlay_command(websocket, command, session)

        elif msg_type == "playback":
            # Playback status update
            state = payload.get("state")
            content_id = payload.get("content_id")
            position_ms = payload.get("position_ms", 0)
            print(f"[OpenCue] Playback: {state} at {position_ms}ms ({content_id})")

            # Update session
            session.content_id = content_id
            session_manager = get_session_manager()

            if state == "playing":
                session_manager.update_position(session, position_ms)
            elif state == "seeked":
                session_manager.handle_seek(session, position_ms)

        elif msg_type == "setMode":
            # Set session mode
            mode = payload.get("mode", "realtime")
            cue_file = payload.get("cueFile")

            session_manager = get_session_manager()
            result = await session_manager.set_mode(session, mode, cue_file)

            await websocket.send(json.dumps({
                "type": "modeSet",
                "payload": result
            }))

        elif msg_type == "loadCueFile":
            # Load a specific cue file
            cue_file_id = payload.get("id")
            if cue_file_id:
                session_manager = get_session_manager()
                result = await session_manager.set_mode(session, "cue_file", cue_file_id)
                await websocket.send(json.dumps({
                    "type": "cueFileLoaded",
                    "payload": result
                }))

        elif msg_type == "listCueFiles":
            # List available cue files
            from cue_manager import get_cue_manager
            manager = get_cue_manager()
            cue_files = [
                {
                    "id": info.path,
                    "title": info.title,
                    "duration_ms": info.duration_ms,
                    "cue_count": info.cue_count,
                    "has_fingerprints": info.has_fingerprints
                }
                for info in manager.get_available()
            ]
            await websocket.send(json.dumps({
                "type": "cueFileList",
                "payload": {"files": cue_files}
            }))

        elif msg_type == "getSessionInfo":
            # Get current session info
            await websocket.send(json.dumps({
                "type": "sessionInfo",
                "payload": {
                    "session_id": session.session_id,
                    "mode": session.mode.value,
                    "synced": session.synced,
                    "cue_file": session.cue_file_id,
                    "content_id": session.content_id
                }
            }))

        elif msg_type == "position":
            # Position update (for cue file mode without audio sync)
            position_ms = payload.get("position_ms", 0)
            session_manager = get_session_manager()
            session_manager.update_position(session, position_ms)

        elif msg_type == "startRecording":
            # Start recording mode
            title = payload.get("title", "")
            content_id = payload.get("content_id", session.content_id or "unknown")
            session_manager = get_session_manager()
            result = session_manager.start_recording(session, title, content_id)
            await websocket.send(json.dumps({
                "type": "recordingStarted",
                "payload": result
            }))

        elif msg_type == "stopRecording":
            # Stop recording and get cue data
            session_manager = get_session_manager()
            result = session_manager.stop_recording(session)

            # Auto-save to cues folder
            if result.get("success") and result.get("cue_data"):
                cue_data = result["cue_data"]
                title = cue_data.get("content", {}).get("title", "recording")
                # Sanitize filename
                safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()
                safe_title = safe_title[:50] if safe_title else "recording"
                filename = f"{safe_title}.opencue"

                cues_dir = Path(__file__).parent / "cues"
                cues_dir.mkdir(exist_ok=True)
                filepath = cues_dir / filename

                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(cue_data, f, indent=2)

                result["saved_to"] = str(filepath)
                print(f"[OpenCue] Cue file saved to: {filepath}")

            await websocket.send(json.dumps({
                "type": "recordingStopped",
                "payload": result
            }))

        elif msg_type == "getRecordingStatus":
            # Get current recording status
            session_manager = get_session_manager()
            status = session_manager.get_recording_status(session)
            await websocket.send(json.dumps({
                "type": "recordingStatus",
                "payload": status
            }))

        elif msg_type == "abortRecording":
            # Abort recording and discard cues
            session_manager = get_session_manager()
            result = session_manager.abort_recording(session)
            await websocket.send(json.dumps({
                "type": "recordingAborted",
                "payload": result
            }))

        elif msg_type == "pauseRecording":
            # Pause recording (keep cues for resume)
            session_manager = get_session_manager()
            result = session_manager.pause_recording(session)
            await websocket.send(json.dumps({
                "type": "recordingPaused",
                "payload": result
            }))

        elif msg_type == "resumeRecording":
            # Resume recording from paused state
            position_ms = payload.get("position_ms", 0)
            session_manager = get_session_manager()
            result = session_manager.resume_recording(session, position_ms)
            await websocket.send(json.dumps({
                "type": "recordingResumed",
                "payload": result
            }))

        else:
            print(f"[OpenCue] Unknown message type: {msg_type}")

    except json.JSONDecodeError as e:
        print(f"[OpenCue] Invalid JSON: {e}")
    except Exception as e:
        print(f"[OpenCue] Error handling message: {e}")
        import traceback
        traceback.print_exc()


async def send_overlay_command(websocket: WebSocketServerProtocol, command: dict, session=None):
    """Send overlay command to extension"""
    message = {
        "type": "overlay",
        "payload": command,
        "timestamp": int(datetime.now().timestamp() * 1000)
    }

    try:
        await websocket.send(json.dumps(message))
        print(f"[OpenCue] Sent overlay: {command.get('action')} "
              f"({command.get('start_ms')}-{command.get('end_ms')}ms)")

        # Record event
        record_event(command)

        # If session is recording, add to recorded cues
        if session and session.recording:
            session_manager = get_session_manager()
            session_manager.add_recorded_cue(session, command)

    except Exception as e:
        print(f"[OpenCue] Error sending overlay command: {e}")


async def broadcast(message: dict):
    """Broadcast message to all connected extensions"""
    if not connections:
        return

    message_json = json.dumps(message)
    await asyncio.gather(
        *[conn.send(message_json) for conn in connections],
        return_exceptions=True
    )


def get_connection_count() -> int:
    """Get number of active connections"""
    return len(connections)


async def start_websocket_server():
    """Start the WebSocket server"""
    global server
    server = await websockets.serve(
        handle_connection,
        WS_HOST,
        WS_PORT
    )
    print(f"[OpenCue] WebSocket server listening on ws://{WS_HOST}:{WS_PORT}")
    await server.wait_closed()


async def stop_websocket_server():
    """Stop the WebSocket server"""
    global server
    if server:
        server.close()
        await server.wait_closed()
        server = None
        print("[OpenCue] WebSocket server stopped")


if __name__ == "__main__":
    # Run standalone for testing
    print("[OpenCue] Starting WebSocket server (standalone)...")
    asyncio.run(start_websocket_server())
