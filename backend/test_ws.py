import asyncio
import websockets

async def test():
    try:
        ws = await websockets.connect('ws://localhost:8765')
        print('Connected!')
        await ws.close()
    except Exception as e:
        print(f'Failed: {e}')

asyncio.run(test())
