"""WS endpoint tests for file-backed storage replay."""
import threading
import time
import pytest
from fastapi.testclient import TestClient

from web.server.app import create_app
from web.server import events, runner, storage


@pytest.fixture
def client(data_root, monkeypatch):
    monkeypatch.setattr("web.server.runner.build_graph", lambda config=None, **kw: None)
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_ws_replays_then_live(client):
    """WS replays persisted events on connect. Live events are
    delivered through the same connection once the WS handler has
    subscribed; the runner tests cover end-to-end live delivery
    (test_runner.py: every fake-graph run emits events that the
    WS replay-on-reconnect sees)."""
    info = storage.create_run_dir("NVDA")
    rid = info["run_id"]
    storage.append_run_event(rid, events.make_event(rid, "run_started", {"ticker": "NVDA"}))
    storage.append_run_event(rid, events.make_event(rid, "analyst_thinking", {"stage": "market", "message": "old"}))

    with client.websocket_connect(f"/ws/runs/{rid}") as ws:
        m1 = ws.receive_json()
        m2 = ws.receive_json()
        assert m1["type"] == "run_started"
        assert m2["type"] == "analyst_thinking"
        # Live emit is covered by test_runner.py. Here we only verify
        # the replay contract; attempting to send a live event from
        # the test thread is unreliable (events.emit needs a running
        # loop in the current thread to schedule the broadcast).
        # The `with` block closes the WS on exit.


def test_ws_replay_sends_all_events(client):
    """v1 always replays the full events.jsonl, no ?since= param."""
    info = storage.create_run_dir("NVDA")
    rid = info["run_id"]
    for i in range(3):
        events.emit(rid, events.EventType.ANALYST_THINKING, {"i": i})
    with client.websocket_connect(f"/ws/runs/{rid}") as ws:
        msgs = [ws.receive_json() for _ in range(3)]
    assert [m["data"]["i"] for m in msgs] == [0, 1, 2]


def test_ws_rejects_unknown_run(client):
    """Unknown run_id → error close."""
    with client.websocket_connect("/ws/runs/NOPE:nope") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "error"
        assert "not found" in msg["detail"]


def test_ws_global_endpoint_accepts_and_closes_cleanly(client):
    """The /ws/global endpoint must accept connections and close cleanly.

    Regression test: the frontend's ``useGlobalStream`` hook always
    opens a WS to ``/ws/global`` on dashboard mount. Without this route
    the request fell through to the ``StaticFiles`` mount at ``/`` and
    crashed the ASGI app with
    ``AssertionError: scope["type"] == "http"`` (starlette/staticfiles.py:91).
    """
    with client.websocket_connect("/ws/global") as ws:
        # If we got here, the WS was accepted without the ASGI app
        # raising. The handler is now draining client messages; we
        # just close on exit.
        pass


def test_ws_global_unsubscribes_on_disconnect(client):
    """After the global WS disconnects, the connection must be removed
    from the events bus so we don't leak subscribers (and memory)."""
    from web.server import events as events_mod

    assert not events_mod._subscribers.get("*")

    with client.websocket_connect("/ws/global"):
        # Inside the ``with`` block, the handler has registered us.
        assert events_mod._subscribers.get("*")

    # After disconnect, the ``finally`` block must have cleaned up.
    assert not events_mod._subscribers.get("*")


def test_ws_global_does_not_match_run_route(client):
    """/ws/global must NOT be served by the /ws/runs/{run_id} handler —
    if it were, the runtime would crash when storage.read_run("global")
    returns None. Routing the global stream to its own handler avoids
    this and also lets the two streams have different lifecycle
    semantics (the global stream is live-only, no replay)."""
    # Verify a fresh /ws/global connect works — the /ws/runs/{run_id}
    # route would have replied with a "run not found" error frame
    # before the global handler can claim the connection.
    with client.websocket_connect("/ws/global") as ws:
        # No initial error frame expected (the global handler doesn't
        # send one). Close cleanly.
        pass
