import json
import threading
import time
import pytest
from fastapi.testclient import TestClient

from web.server.app import create_app
from web.server import db, runner


@pytest.fixture
def client(temp_db, monkeypatch):
    monkeypatch.setattr("web.server.runner.build_graph", lambda config=None: None)
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_ws_replays_then_live(client, monkeypatch):
    # Insert a run + 2 events directly
    rid = db.create_run(ticker="NVDA", idempotency_key="NVDA:ws")

    db.append_event(rid, "run_started", {"ticker": "NVDA"})
    db.append_event(rid, "analyst_thinking", {"stage": "market", "message": "old"})

    # Open the WS in a thread
    received = []
    stop = threading.Event()

    def listen():
        with client.websocket_connect(f"/ws/runs/{rid}") as ws:
            while not stop.is_set():
                try:
                    msg = ws.receive_json()
                    received.append(msg)
                except Exception:
                    break
    t = threading.Thread(target=listen, daemon=True)
    t.start()
    time.sleep(0.2)

    # Now emit a live event via the broadcast function the app registered
    from web.server import events
    events.emit(rid, "decision", {"action": "BUY", "target": 200.0})
    time.sleep(0.2)
    stop.set()
    t.join(timeout=2)

    types = [m["type"] for m in received]
    assert "run_started" in types
    assert "analyst_thinking" in types
    assert "decision" in types


def test_ws_replays_only_gap_with_since(client, monkeypatch):
    rid = db.create_run(ticker="AAPL", idempotency_key="AAPL:gap")
    e1 = db.append_event(rid, "run_started", {})
    e2 = db.append_event(rid, "analyst_thinking", {"stage": "market"})

    received = []
    stop = threading.Event()

    def listen():
        with client.websocket_connect(f"/ws/runs/{rid}?since={e1}") as ws:
            while not stop.is_set():
                try:
                    msg = ws.receive_json()
                    received.append(msg)
                except Exception:
                    break
    t = threading.Thread(target=listen, daemon=True)
    t.start()
    time.sleep(0.2)
    stop.set()
    t.join(timeout=2)

    # Only the analyst_thinking event (e2) should have been replayed
    types = [m["type"] for m in received]
    assert types == ["analyst_thinking"]
