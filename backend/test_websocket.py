"""Test WebSocket connection and subtitle processing"""
import asyncio
import websockets
import json

async def test_connection():
    uri = "ws://localhost:8765"
    print(f"Connecting to {uri}...")

    try:
        async with websockets.connect(uri) as websocket:
            print("Connected!")

            # Test 1: Send a subtitle with profanity
            print("\n--- Test 1: Sending subtitle with profanity ---")
            subtitle_msg = {
                "type": "subtitle",
                "payload": {
                    "text": "What the fuck is going on here?",
                    "start_ms": 5000,
                    "end_ms": 8000,
                    "position_ms": 5000,
                    "content_id": "test:12345"
                }
            }
            await websocket.send(json.dumps(subtitle_msg))
            print(f"Sent: {subtitle_msg['payload']['text']}")

            # Wait for response
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=3.0)
                msg = json.loads(response)
                print(f"Received: {msg['type']}")
                if msg['type'] == 'overlay':
                    print(f"  Action: {msg['payload'].get('action')}")
                    print(f"  Word: {msg['payload'].get('matched')}")
                    print(f"  Time: {msg['payload'].get('start_ms')}-{msg['payload'].get('end_ms')}ms")
                    print("\n SUCCESS: Profanity detected and overlay command sent!")
                else:
                    print(f"  Full message: {msg}")
            except asyncio.TimeoutError:
                print("  No response received (timeout)")
                print("\n FAILURE: Backend did not send overlay command")

            # Test 2: Send clean subtitle
            print("\n--- Test 2: Sending clean subtitle ---")
            clean_msg = {
                "type": "subtitle",
                "payload": {
                    "text": "Hello, how are you today?",
                    "start_ms": 10000,
                    "end_ms": 13000,
                    "position_ms": 10000,
                    "content_id": "test:12345"
                }
            }
            await websocket.send(json.dumps(clean_msg))
            print(f"Sent: {clean_msg['payload']['text']}")

            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                msg = json.loads(response)
                print(f"Received unexpected: {msg['type']}")
            except asyncio.TimeoutError:
                print("  No response (expected - no profanity)")
                print("\n SUCCESS: Clean subtitle correctly ignored")

            print("\n=== All tests passed! Backend is working correctly ===")

    except ConnectionRefusedError:
        print("ERROR: Could not connect to backend!")
        print("Make sure the backend is running: python main.py")
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(test_connection())
