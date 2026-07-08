"""EventBroadcaster, session-cookie auth, and the SSE endpoint."""

import asyncio
import json
import threading

import pytest

fastapi = pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from tradingagents.pro.alerting import AlertManager  # noqa: E402
from tradingagents.pro.dashboard.app import DashboardState, create_app  # noqa: E402
from tradingagents.pro.dashboard.events import (  # noqa: E402
    BroadcastAlertSink,
    EventBroadcaster,
)


def drain(broadcaster, last_event_id=None, n=1, extra=None):
    """Run an event loop that subscribes and collects n frames."""

    async def collect():
        broadcaster.bind_loop(asyncio.get_running_loop())
        if extra:
            extra()
        frames = []
        agen = broadcaster.subscribe(last_event_id)
        async for frame in agen:
            frames.append(frame)
            if len([f for f in frames if not f.startswith(":")]) >= n:
                break
        await agen.aclose()
        return frames

    return asyncio.run(collect())


class TestBroadcaster:
    def test_publish_before_loop_binds_buffers_to_ring(self):
        broadcaster = EventBroadcaster()
        broadcaster.publish("run", {"run_id": "r1"})  # no loop bound: no error
        frames = drain(broadcaster, last_event_id=0, n=1)
        assert "event: run" in frames[0] and '"run_id": "r1"' in frames[0]

    def test_replay_honors_last_event_id(self):
        broadcaster = EventBroadcaster()
        first = broadcaster.publish("run", {"i": 1})
        broadcaster.publish("run", {"i": 2})
        frames = drain(broadcaster, last_event_id=first.id, n=1)
        assert '"i": 2' in frames[0] and '"i": 1' not in "".join(frames)

    def test_threaded_publishers_deliver_exactly_once_in_order(self):
        broadcaster = EventBroadcaster()
        n_threads, per_thread = 8, 25

        def blast():
            for _ in range(per_thread):
                broadcaster.publish("run", {})

        def start_threads():
            for t in [threading.Thread(target=blast) for _ in range(n_threads)]:
                t.start()

        frames = drain(broadcaster, last_event_id=0,
                       n=n_threads * per_thread, extra=start_threads)
        ids = [int(f.split("id: ")[1].split("\n")[0])
               for f in frames if f.startswith("id:")]
        assert len(ids) == n_threads * per_thread
        assert ids == sorted(ids) and len(set(ids)) == len(ids)

    def test_stalled_subscriber_drops_oldest_not_publisher(self):
        broadcaster = EventBroadcaster(queue_size=4)

        async def scenario():
            broadcaster.bind_loop(asyncio.get_running_loop())
            agen = broadcaster.subscribe(None)
            first = await agen.__anext__()  # queue registered after first pull?
            return first

        # simpler deterministic check at the queue level:
        async def overflow():
            broadcaster.bind_loop(asyncio.get_running_loop())
            agen = broadcaster.subscribe(None)
            # subscription registers immediately on first __anext__ call setup;
            # publish 10 events while nobody drains
            task = asyncio.ensure_future(agen.__anext__())
            await asyncio.sleep(0)  # let subscribe() register the queue
            for i in range(10):
                broadcaster.publish("run", {"i": i})
            frames = [await task]
            for _ in range(3):
                frames.append(await agen.__anext__())
            await agen.aclose()
            return frames

        frames = asyncio.run(overflow())
        payloads = [json.loads(f.split("data: ")[1].strip()) for f in frames]
        # queue held 4 of 10; the oldest were dropped, order preserved
        assert [p["i"] for p in payloads] == [6, 7, 8, 9]

    def test_alert_sink_bridges_to_stream(self):
        broadcaster = EventBroadcaster()
        manager = AlertManager(sinks=[BroadcastAlertSink(broadcaster)])
        manager.emit("critical", "unit_test", "bridged")
        frames = drain(broadcaster, last_event_id=0, n=1)
        assert "event: alert" in frames[0] and "bridged" in frames[0]

    def test_alert_sink_never_raises_into_manager(self):
        broken = EventBroadcaster()
        broken.publish = lambda *a, **k: (_ for _ in ()).throw(RuntimeError())
        manager = AlertManager(sinks=[BroadcastAlertSink(broken)])
        manager.emit("info", "x", "y")  # isolation: no exception escapes


@pytest.fixture()
def secured_client():
    app = create_app(DashboardState(), api_token="secret-token")
    return TestClient(app)


class TestAuthMatrix:
    def test_static_shell_and_healthz_open(self, secured_client):
        assert secured_client.get("/").status_code == 200
        assert secured_client.get("/healthz").json() == {"status": "ok"}

    def test_api_requires_key(self, secured_client):
        assert secured_client.get("/api/overview").status_code == 401
        ok = secured_client.get("/api/overview",
                                headers={"X-API-Key": "secret-token"})
        assert ok.status_code == 200

    def test_session_cookie_flow(self, secured_client):
        assert secured_client.post("/api/session").status_code == 401
        minted = secured_client.post("/api/session",
                                     headers={"X-API-Key": "secret-token"})
        assert minted.status_code == 200
        cookie = minted.cookies.get("pro_session")
        assert cookie
        # cookie alone now authenticates (TestClient persists cookies)
        assert secured_client.get("/api/overview").status_code == 200

    def test_bogus_cookie_rejected(self, secured_client):
        secured_client.cookies.set("pro_session", "forged")
        assert secured_client.get("/api/overview").status_code == 401

    def test_open_mode_without_token(self):
        client = TestClient(create_app(DashboardState()))
        assert client.get("/api/overview").status_code == 200
        session = client.post("/api/session").json()
        assert session == {"authenticated": True, "auth_required": False}


class TestSSEEndpoint:
    def test_stream_replays_and_delivers(self):
        state = DashboardState()
        app = create_app(state, api_token="secret-token")
        with TestClient(app) as client:
            client.post("/api/session", headers={"X-API-Key": "secret-token"})
            state.broadcaster.publish("run", {"run_id": "replayed"})
            response = client.get(
                "/api/stream",
                params={"last_event_id": "0", "max_events": "1"},
            )
            assert response.status_code == 200
            content_type = response.headers["content-type"]
            assert content_type.startswith("text/event-stream")
            assert response.headers["x-accel-buffering"] == "no"
            assert "event: run" in response.text and "replayed" in response.text

    def test_stream_requires_auth(self, secured_client):
        assert secured_client.get("/api/stream").status_code == 401


class TestDevCors:
    def test_cors_only_with_dev_flag(self, monkeypatch):
        monkeypatch.setenv("PRO_DASHBOARD_DEV", "1")
        client = TestClient(create_app(DashboardState(), api_token="tok"))
        response = client.options(
            "/api/overview",
            headers={"Origin": "http://localhost:5173",
                     "Access-Control-Request-Method": "GET",
                     "Access-Control-Request-Headers": "x-api-key"},
        )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
        # 401s still carry CORS headers so the dev SPA can react
        denied = client.get("/api/overview",
                            headers={"Origin": "http://localhost:5173"})
        assert denied.status_code == 401
        assert "access-control-allow-origin" in denied.headers

    def test_no_cors_by_default(self, secured_client):
        response = secured_client.get(
            "/healthz", headers={"Origin": "http://localhost:5173"})
        assert "access-control-allow-origin" not in response.headers
