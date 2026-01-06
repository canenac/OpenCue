"""
OpenCue - WebSocket Server

Handles real-time communication with browser extensions.
"""

import asyncio
import json
from datetime import datetime
from typing import Set

import websockets
from websockets.server import WebSocketServerProtocol

from overlay_engine import process_subtitle, record_event

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

    try:
        async for message in websocket:
            await handle_message(websocket, message)
    except websockets.exceptions.ConnectionClosed as e:
        print(f"[OpenCue] Connection closed: {client_id} ({e.code})")
    finally:
        connections.discard(websocket)
        print(f"[OpenCue] Extension disconnected: {client_id}")


async def handle_message(websocket: WebSocketServerProtocol, raw_message: str):
    """Handle incoming message from extension"""
    try:
        message = json.loads(raw_message)
        msg_type = message.get("type")
        payload = message.get("payload", {})

        print(f"[OpenCue] Received: {msg_type}")

        if msg_type == "subtitle":
            # Process subtitle and check for overlay triggers
            overlay_commands = await process_subtitle(
                text=payload.get("text", ""),
                start_ms=payload.get("start_ms", 0),
                end_ms=payload.get("end_ms", 0),
                content_id=payload.get("content_id", "")
            )

            # Send overlay commands back to extension
            for command in overlay_commands:
                await send_overlay_command(websocket, command)

        elif msg_type == "playback":
            # Log playback status
            state = payload.get("state")
            content_id = payload.get("content_id")
            position_ms = payload.get("position_ms")
            print(f"[OpenCue] Playback: {state} at {position_ms}ms ({content_id})")

        else:
            print(f"[OpenCue] Unknown message type: {msg_type}")

    except json.JSONDecodeError as e:
        print(f"[OpenCue] Invalid JSON: {e}")
    except Exception as e:
        print(f"[OpenCue] Error handling message: {e}")


async def send_overlay_command(websocket: WebSocketServerProtocol, command: dict):
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
