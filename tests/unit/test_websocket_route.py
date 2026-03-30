import asyncio

from agent_os.backend.routes import websocket as websocket_route


class _FakeWebSocket:
    def __init__(self) -> None:
        self.accepted = False
        self.sent: list[dict] = []
        self.closed = False

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)

    async def close(self) -> None:
        self.closed = True


def test_websocket_endpoint_swallows_cancelled_error(monkeypatch):
    run_id = "test-run"
    fake_ws = _FakeWebSocket()
    websocket_route.runs[run_id] = {"status": "running", "events": []}

    async def _raise_cancelled(_: float) -> None:
        raise asyncio.CancelledError()

    monkeypatch.setattr(websocket_route.asyncio, "sleep", _raise_cancelled)

    try:
        asyncio.run(websocket_route.websocket_endpoint(fake_ws, run_id))
    finally:
        websocket_route.runs.pop(run_id, None)

    assert fake_ws.accepted is True
