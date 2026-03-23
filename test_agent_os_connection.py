import asyncio
import websockets
import json

async def test_ws():
    uri = "ws://localhost:8001/ws/stream/test_run"
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected to WebSocket")
            while True:
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    data = json.loads(message)
                    print(f"Received: {data['type']} from {data.get('agent', 'system')}")
                    if data['type'] == 'system' and 'completed' in data['message']:
                        break
                except asyncio.TimeoutError:
                    print("Timeout waiting for message")
                    break
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    # We need to trigger a run first to make the ID valid in the store
    import requests
    try:
        resp = requests.post("http://localhost:8001/api/run/scan", json={})
        run_id = resp.json()["run_id"]
        print(f"Triggered run: {run_id}")
        
        # Now connect to the stream
        uri = f"ws://localhost:8001/ws/stream/{run_id}"
        async def run_test():
            async with websockets.connect(uri) as ws:
                print("Stream connected")
                async for msg in ws:
                    print(f"Msg: {msg[:100]}...")
        asyncio.run(run_test())
    except Exception as e:
        print(f"Error: {e}")
