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
        cookie = minted.cookies.get("__session")
        assert cookie
        # cookie alone now authenticates (TestClient persists cookies)
        assert secured_client.get("/api/overview").status_code == 200

    def test_bogus_cookie_rejected(self, secured_client):
        secured_client.cookies.set("__session", "forged")
        assert secured_client.get("/api/overview").status_code == 401
        # structurally valid shape but wrong signature
        secured_client.cookies.set("__session", "99999999999.deadbeef")
        assert secured_client.get("/api/overview").status_code == 401

    def test_session_survives_process_restart(self, secured_client):
        """Regression: sessions were an in-process set, so Cloud Run
        scale-to-zero / redeploys logged the operator out constantly. The
        signed cookie must authenticate against a FRESH app instance."""
        minted = secured_client.post("/api/session",
                                     headers={"X-API-Key": "secret-token"})
        cookie = minted.cookies.get("__session")
        assert cookie
        reborn = TestClient(create_app(DashboardState(),
                                       api_token="secret-token"))
        reborn.cookies.set("__session", cookie)
        assert reborn.get("/api/overview").status_code == 200
        # a different token secret invalidates every outstanding session
        rotated = TestClient(create_app(DashboardState(), api_token="other"))
        rotated.cookies.set("__session", cookie)
        assert rotated.get("/api/overview").status_code == 401

    def test_cookie_reestablishes_session_on_boot(self, secured_client):
        """Regression: a Google user's page reload calls POST /api/session
        with ONLY the session cookie (no header, no fresh ID token) — it
        must re-establish, not bounce to the login screen."""
        minted = secured_client.post("/api/session",
                                     headers={"X-API-Key": "secret-token"})
        cookie = minted.cookies.get("__session")
        reloaded = TestClient(create_app(DashboardState(),
                                         api_token="secret-token"))
        reloaded.cookies.set("__session", cookie)
        again = reloaded.post("/api/session")  # no credentials but the cookie
        assert again.status_code == 200
        # sliding TTL: a fresh cookie is set (value only differs when the
        # clock ticks — expiry+hmac are deterministic per second)
        assert "set-cookie" in again.headers
        assert reloaded.get("/api/overview").status_code == 200
        # a bogus cookie still cannot mint anything
        forged = TestClient(create_app(DashboardState(),
                                       api_token="secret-token"))
        forged.cookies.set("__session", "99999999999.deadbeef")
        assert forged.post("/api/session").status_code == 401

    def test_expired_session_rejected(self, secured_client, monkeypatch):
        minted = secured_client.post("/api/session",
                                     headers={"X-API-Key": "secret-token"})
        cookie = minted.cookies.get("__session")
        future = __import__("time").time() + 8 * 24 * 3600  # beyond 7d TTL
        monkeypatch.setattr("time.time", lambda: future)
        fresh = TestClient(create_app(DashboardState(),
                                      api_token="secret-token"))
        fresh.cookies.set("__session", cookie)
        assert fresh.get("/api/overview").status_code == 401

    def test_open_mode_without_token(self):
        client = TestClient(create_app(DashboardState()))
        assert client.get("/api/overview").status_code == 200
        session = client.post("/api/session").json()
        assert session == {"authenticated": True, "auth_required": False,
                           "identity": None}


GOOGLE_ENV = {
    "PRO_FIREBASE_PROJECT_ID": "demo-project",
    "PRO_ALLOWED_EMAILS": "Trader@Example.com",  # mixed case: compare folded
    "PRO_FIREBASE_WEB_CONFIG": '{"apiKey": "public", "projectId": "demo-project"}',
}


class TestGoogleSession:
    """Google sign-in: Bearer ID-token verification gated on the email
    allowlist (fail closed at every branch). The verifier is monkeypatched —
    these tests never hit Google's cert endpoint."""

    def _client(self, monkeypatch, claims=None, error=None, env=GOOGLE_ENV):
        import tradingagents.pro.dashboard.app as app_module

        for key, value in env.items():
            monkeypatch.setenv(key, value)

        def fake_verify(id_token, audience):
            assert audience == "demo-project"
            if error is not None:
                raise error
            return claims

        monkeypatch.setattr(app_module, "_verify_firebase_token", fake_verify)
        return TestClient(create_app(DashboardState(), api_token="secret-token"))

    def test_allowlisted_email_mints_cookie(self, monkeypatch):
        client = self._client(monkeypatch, claims={
            "email": "trader@example.com", "email_verified": True})
        minted = client.post("/api/session",
                             headers={"Authorization": "Bearer good"})
        assert minted.status_code == 200
        assert minted.json()["identity"] == "trader@example.com"
        assert minted.cookies.get("__session")
        assert client.get("/api/overview").status_code == 200  # cookie works

    def test_non_allowlisted_email_403(self, monkeypatch):
        client = self._client(monkeypatch, claims={
            "email": "intruder@example.com", "email_verified": True})
        denied = client.post("/api/session",
                             headers={"Authorization": "Bearer good"})
        assert denied.status_code == 403
        assert client.get("/api/overview").status_code == 401  # no cookie

    def test_unverified_email_401(self, monkeypatch):
        client = self._client(monkeypatch, claims={
            "email": "trader@example.com", "email_verified": False})
        assert client.post(
            "/api/session", headers={"Authorization": "Bearer good"}
        ).status_code == 401

    def test_invalid_token_401(self, monkeypatch):
        client = self._client(monkeypatch, error=ValueError("expired"))
        assert client.post(
            "/api/session", headers={"Authorization": "Bearer bad"}
        ).status_code == 401

    def test_bearer_ignored_when_google_not_configured(self, monkeypatch):
        # no PRO_FIREBASE_* env: bearer must NOT open a side door
        for key in GOOGLE_ENV:
            monkeypatch.delenv(key, raising=False)
        client = TestClient(create_app(DashboardState(), api_token="secret-token"))
        assert client.post(
            "/api/session", headers={"Authorization": "Bearer anything"}
        ).status_code == 401

    def test_fail_closed_without_allowlist(self, monkeypatch):
        env = dict(GOOGLE_ENV, PRO_ALLOWED_EMAILS="")
        client = self._client(monkeypatch, claims={
            "email": "trader@example.com", "email_verified": True}, env=env)
        # google disabled entirely → bearer path rejected, config says so
        assert client.post(
            "/api/session", headers={"Authorization": "Bearer good"}
        ).status_code == 401
        assert client.get("/api/auth/config").json()["google"] is False

    def test_jwt_cookie_carries_identity_across_reload(self, monkeypatch):
        """The session cookie is a real HS256 JWT whose signed `sub` claim
        restores the Google identity on reload (cookie-only re-establish)."""
        import base64
        import json

        client = self._client(monkeypatch, claims={
            "email": "trader@example.com", "email_verified": True})
        minted = client.post("/api/session",
                             headers={"Authorization": "Bearer good"})
        cookie = minted.cookies.get("__session")
        header_b64, payload_b64, _sig = cookie.split(".")
        decode = lambda part: json.loads(  # noqa: E731
            base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
        assert decode(header_b64) == {"alg": "HS256", "typ": "JWT"}
        payload = decode(payload_b64)
        assert payload["sub"] == "trader@example.com"
        assert payload["exp"] > payload["iat"]
        # reload: cookie-only POST restores the identity from the claim
        again = client.post("/api/session")
        assert again.status_code == 200
        assert again.json()["identity"] == "trader@example.com"

    def test_api_key_path_untouched(self, monkeypatch):
        client = self._client(monkeypatch, claims={
            "email": "trader@example.com", "email_verified": True})
        minted = client.post("/api/session",
                             headers={"X-API-Key": "secret-token"})
        assert minted.status_code == 200
        assert minted.json()["identity"] is None  # token sessions carry none

    def test_auth_config_shapes(self, monkeypatch):
        google = self._client(monkeypatch, claims={})
        config = google.get("/api/auth/config").json()
        assert config == {
            "auth_required": True, "google": True,
            "firebase": {"apiKey": "public", "projectId": "demo-project"},
            "stream_url": None,
        }
        for key in GOOGLE_ENV:
            monkeypatch.delenv(key, raising=False)
        plain = TestClient(create_app(DashboardState(), api_token="tok"))
        assert plain.get("/api/auth/config").json() == {
            "auth_required": True, "google": False, "firebase": None,
            "stream_url": None}


class TestDirectStreamTickets:
    """Direct-SSE auth for Firebase Hosting deployments (Hosting's proxy
    can't carry SSE): single-use short-TTL tickets minted by an
    authenticated session, consumed on first use."""

    def _client(self, monkeypatch, state=None):
        monkeypatch.setenv("PRO_STREAM_DIRECT_URL", "https://svc.run.app")
        monkeypatch.setenv("PRO_STREAM_ALLOWED_ORIGIN", "https://site.web.app")
        return TestClient(create_app(state or DashboardState(),
                                     api_token="secret-token"))

    def test_ticket_flow_single_use(self, monkeypatch):
        state = DashboardState()
        with self._client(monkeypatch, state) as client:
            # minting requires auth
            assert client.get("/api/stream/ticket").status_code == 401
            client.post("/api/session", headers={"X-API-Key": "secret-token"})
            ticket = client.get("/api/stream/ticket").json()["ticket"]

            # a fresh browser context: no cookie, ticket alone authenticates
            bare = TestClient(client.app)
            state.broadcaster.publish("run", {"run_id": "r1"})
            ok = bare.get("/api/stream", params={
                "ticket": ticket, "last_event_id": "0", "max_events": "1"})
            assert ok.status_code == 200 and "event: run" in ok.text
            # consumed: the same ticket never authenticates twice
            assert bare.get("/api/stream", params={
                "ticket": ticket, "max_events": "1"}).status_code == 401

    def test_expired_ticket_rejected(self, monkeypatch):
        import tradingagents.pro.dashboard.app  # noqa: F401 — patch target

        with self._client(monkeypatch) as client:
            client.post("/api/session", headers={"X-API-Key": "secret-token"})
            ticket = client.get("/api/stream/ticket").json()["ticket"]
            future = __import__("time").monotonic() + 120  # beyond the 60s TTL
            monkeypatch.setattr("time.monotonic", lambda: future)
            bare = TestClient(client.app)
            assert bare.get("/api/stream", params={
                "ticket": ticket, "max_events": "1"}).status_code == 401

    def test_ticket_never_opens_other_routes(self, monkeypatch):
        with self._client(monkeypatch) as client:
            client.post("/api/session", headers={"X-API-Key": "secret-token"})
            ticket = client.get("/api/stream/ticket").json()["ticket"]
            bare = TestClient(client.app)
            assert bare.get("/api/overview",
                            params={"ticket": ticket}).status_code == 401

    def test_cors_header_only_for_allowed_origin(self, monkeypatch):
        state = DashboardState()
        with self._client(monkeypatch, state) as client:
            client.post("/api/session", headers={"X-API-Key": "secret-token"})
            state.broadcaster.publish("run", {"run_id": "r1"})
            for origin, expected in [("https://site.web.app", True),
                                     ("https://evil.example", False)]:
                ticket = client.get("/api/stream/ticket").json()["ticket"]
                response = TestClient(client.app).get(
                    "/api/stream",
                    params={"ticket": ticket, "last_event_id": "0",
                            "max_events": "1"},
                    headers={"Origin": origin})
                assert (response.headers.get("access-control-allow-origin")
                        == "https://site.web.app") is expected

    def test_disabled_without_env(self):
        client = TestClient(create_app(DashboardState(), api_token="tok"))
        client.post("/api/session", headers={"X-API-Key": "tok"})
        assert client.get("/api/stream/ticket").status_code == 404
        assert client.get("/api/auth/config").json()["stream_url"] is None


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
