"""FastAPI application for the Pro dashboard.

Requires the ``dashboard`` extra (``pip install "tradingagents[dashboard]"``).
The app is a thin shell: every endpoint delegates to the tested view-model
functions in service.py; the SPA (or the legacy single page) renders them.

Auth model: all ``/api/*`` routes require ``X-API-Key`` when a token is
configured. ``POST /api/session`` exchanges the key for an HttpOnly cookie
so browser-native transports that cannot set headers (EventSource,
``<a download>``) still authenticate. Static shell and ``/healthz`` are
open — they contain no data.

Google sign-in (optional): when ``PRO_FIREBASE_PROJECT_ID`` and a non-empty
``PRO_ALLOWED_EMAILS`` allowlist are both set, ``POST /api/session`` also
accepts ``Authorization: Bearer <firebase-id-token>`` — verified against
Google's public certs via google-auth (already a dependency), then gated on
``email_verified`` + the allowlist — and mints the same session cookie.
Fail closed: a project id without an allowlist keeps Google sign-in
disabled. ``GET /api/auth/config`` (open) tells the SPA which login UI to
render; ``PRO_FIREBASE_WEB_CONFIG`` carries the public Firebase web config.

Run locally:
    uvicorn --factory tradingagents.pro.dashboard.app:create_default_app
"""

# NOTE: no `from __future__ import annotations` here — FastAPI resolves
# endpoint annotations at runtime against module globals, and Request/
# Response are imported lazily inside create_app (fastapi is an optional
# extra). Deferred annotations would demote them to query params.
from dataclasses import dataclass, field
from importlib import resources

from tradingagents.pro.backtest import BacktestResult
from tradingagents.pro.dashboard import marketdata as md, service
from tradingagents.pro.dashboard.events import EventBroadcaster
from tradingagents.pro.dashboard.intel import IntelService
from tradingagents.pro.dashboard.prefs import PrefsStore
from tradingagents.pro.dashboard.recorder import PipelineRecorder, RunRecord
from tradingagents.pro.dashboard.ticker import TickCache
from tradingagents.pro.memory import ProMemory

# "__session" is the ONLY cookie Firebase Hosting's CDN forwards to a
# Cloud Run backend — any other name is silently stripped from requests,
# which turns every cookie-authenticated call into a 401 behind Hosting
# (observed live: successful Google sign-in bounced straight back to the
# login screen). Plain deployments don't care what it's called.
SESSION_COOKIE = "__session"


def _verify_firebase_token(id_token: str, audience: str) -> dict:
    """Verify a Firebase ID token and return its claims. Module-level so
    tests can monkeypatch it (the repo's injectable-fakes pattern); raises
    ValueError on any invalid/expired/wrong-audience token."""
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token as google_id_token

    return google_id_token.verify_firebase_token(
        id_token, google_requests.Request(), audience=audience)


@dataclass
class DashboardState:
    recorder: PipelineRecorder = field(default_factory=PipelineRecorder)
    memory: ProMemory = field(default_factory=ProMemory)
    backtest: BacktestResult | None = None
    monte_carlo = None
    router = None            # ExecutionRouter, when attached to live/paper loop
    equity: float | None = None
    broadcaster: EventBroadcaster = field(default_factory=EventBroadcaster)
    marketdata: md.MarketDataService = field(default_factory=md.MarketDataService)
    ticks: TickCache | None = None  # set in __post_init__
    prefs: PrefsStore = field(default_factory=PrefsStore)
    intel: IntelService = field(default_factory=IntelService)
    trigger = None            # PipelineTrigger, when a service loop is attached
    metrics = None            # MetricsRegistry, when a service loop is attached
    arming = None             # ArmingStore, when live wiring is present
    alerts = None             # AlertManager, when a service loop is attached

    @property
    def runs(self) -> list[RunRecord]:
        return self.recorder.runs

    def latest_run(self) -> RunRecord | None:
        return self.runs[-1] if self.runs else None

    def latest_run_for(self, symbol: str) -> RunRecord | None:
        """Newest run for one symbol — the per-symbol decision board
        (trader review G1) must not lose a gold ticket because a BTC
        run happened afterwards."""
        for run in reversed(self.runs):
            if run.symbol == symbol:
                return run
        return None


def create_app(state: DashboardState | None = None, api_token: str | None = None):
    """``api_token`` (or env PRO_DASHBOARD_TOKEN) enables auth on /api/*.
    Unset = open, for localhost dev only (SEC-01) — deployment templates
    set the token and bind loopback."""
    import asyncio
    import hmac
    import os
    import secrets
    from contextlib import asynccontextmanager

    from fastapi import FastAPI, HTTPException, Request, Response
    from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

    state = state or DashboardState()
    token = api_token if api_token is not None else os.environ.get("PRO_DASHBOARD_TOKEN")

    # Sessions are STATELESS, cookie-based JWTs (HS256, stdlib — the repo
    # avoids new dependencies): header.payload.signature signed with a key
    # derived from the API token, so a session survives process restarts,
    # redeploys, and Cloud Run scale-to-zero, and the payload carries the
    # signed identity (`sub`) across reloads. Rotating PRO_DASHBOARD_TOKEN
    # invalidates every outstanding session.
    SESSION_TTL_SECONDS = 7 * 24 * 3600
    _jwt_key = (hmac.new(token.encode(), b"pro-session-jwt", "sha256").digest()
                if token else b"")

    def _b64url(data: bytes) -> str:
        import base64 as _base64

        return _base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    def _b64url_decode(text: str) -> bytes:
        import base64 as _base64

        return _base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))

    def _mint_session(identity: "str | None" = None) -> str:
        import json as _json
        import time as _time

        now = int(_time.time())
        header = _b64url(_json.dumps(
            {"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
        payload = _b64url(_json.dumps(
            {"iss": "tradingagents-pro", "sub": identity or "api-token",
             "iat": now, "exp": now + SESSION_TTL_SECONDS},
            separators=(",", ":")).encode())
        signing_input = f"{header}.{payload}"
        signature = _b64url(hmac.new(_jwt_key, signing_input.encode(),
                                     "sha256").digest())
        return f"{signing_input}.{signature}"

    def _session_claims(cookie: str) -> "dict | None":
        """Verify the JWT cookie; returns its claims or None."""
        import json as _json
        import time as _time

        parts = cookie.split(".")
        if len(parts) != 3:
            return None
        signing_input = f"{parts[0]}.{parts[1]}"
        expected = _b64url(hmac.new(_jwt_key, signing_input.encode(),
                                    "sha256").digest())
        if not hmac.compare_digest(parts[2], expected):
            return None
        try:
            claims = _json.loads(_b64url_decode(parts[1]))
        except (ValueError, UnicodeDecodeError):
            return None
        if not isinstance(claims.get("exp"), int) or claims["exp"] <= _time.time():
            return None
        return claims

    def _session_valid(cookie: str) -> bool:
        return _session_claims(cookie) is not None

    # Google sign-in (optional). Fail closed: BOTH the project id (token
    # audience) and a non-empty email allowlist are required — a project id
    # alone would admit any Google account on earth.
    firebase_project = os.environ.get("PRO_FIREBASE_PROJECT_ID", "").strip()
    allowed_emails = {
        email.strip().lower()
        for email in os.environ.get("PRO_ALLOWED_EMAILS", "").split(",")
        if email.strip()
    }
    google_enabled = bool(firebase_project and allowed_emails)

    # Direct SSE (optional): Firebase Hosting's proxy buffers responses and
    # cannot carry Server-Sent Events (observed live: /api/stream → 503
    # behind Hosting). When BOTH are set, the SPA connects its EventSource
    # straight to the Cloud Run origin, authenticated by a short-lived
    # single-use ticket minted through the normal (cookie) session:
    #   PRO_STREAM_DIRECT_URL      public Cloud Run URL (no trailing slash)
    #   PRO_STREAM_ALLOWED_ORIGIN  the Hosting origin allowed via CORS
    # In-process ticket store is safe: deployments enforce max-instances=1
    # (the same single-writer invariant that guards /data).
    stream_direct_url = os.environ.get("PRO_STREAM_DIRECT_URL", "").strip().rstrip("/")
    stream_allowed_origin = os.environ.get(
        "PRO_STREAM_ALLOWED_ORIGIN", "").strip().rstrip("/")
    stream_direct = bool(stream_direct_url and stream_allowed_origin)
    stream_tickets: dict[str, float] = {}  # ticket -> monotonic expiry
    STREAM_TICKET_TTL = 60.0
    firebase_web_config = None
    if google_enabled:
        import json as _json

        raw_config = os.environ.get("PRO_FIREBASE_WEB_CONFIG", "")
        try:
            firebase_web_config = _json.loads(raw_config) if raw_config else None
        except ValueError:
            firebase_web_config = None
        if firebase_web_config is None:
            import logging

            logging.getLogger(__name__).warning(
                "PRO_FIREBASE_WEB_CONFIG missing/invalid — Google sign-in "
                "disabled (the SPA needs the public web config to start "
                "the OAuth popup)"
            )
            google_enabled = False
    elif firebase_project and not allowed_emails:
        import logging

        logging.getLogger(__name__).warning(
            "PRO_FIREBASE_PROJECT_ID set without PRO_ALLOWED_EMAILS — "
            "Google sign-in stays DISABLED (fail closed; an empty allowlist "
            "would admit any Google account)"
        )

    @asynccontextmanager
    async def lifespan(app):
        state.broadcaster.bind_loop(asyncio.get_running_loop())
        pollers = []
        try:
            from tradingagents.pro.dashboard.ticker import (
                PriceAlertEngine,
                QuoteTickPoller,
            )

            def _emit_price_alert(severity, event, text, **labels):
                # AlertManager (Telegram/webhook/log/notification) when a
                # loop is attached; SSE + notification store always
                if state.alerts is not None:
                    state.alerts.emit(severity, event, text, **labels)
                    return
                from datetime import datetime, timezone

                now = datetime.now(timezone.utc).isoformat()
                state.prefs.add_notification(
                    severity=severity, event=event, text=text, time=now)
                state.broadcaster.publish("alert", {
                    "severity": severity, "event": event,
                    "text": text, "time": now,
                })

            alert_engine = PriceAlertEngine(state.prefs, _emit_price_alert)

            # one poller per live symbol whose vendor supports quotes;
            # registry access runs the vendor probes (logged) exactly once
            for spec in state.marketdata.registry.values():
                if spec.live and spec.source in ("delta_exchange", "oanda_gold"):
                    poller = QuoteTickPoller(
                        spec.feed_factory(), state.broadcaster,
                        symbol=spec.vendor_symbol, display_symbol=spec.symbol,
                        cache=state.ticks,
                        alert_engine=alert_engine,
                    )
                    poller.start()
                    pollers.append(poller)
        except Exception:  # a broken tick feed must never block the app
            import logging

            logging.getLogger(__name__).exception("tick pollers not started")
        yield
        for poller in pollers:
            poller.stop()

    app = FastAPI(title="TradingAgents Pro Dashboard", lifespan=lifespan)
    app.state.dashboard = state

    def _consume_stream_ticket(request: Request) -> bool:
        """Single-use, short-TTL ticket auth for the direct-SSE path only.
        Consumed on first validation — a replayed URL is rejected."""
        import time as _time

        supplied = request.query_params.get("ticket", "")
        if not (stream_direct and supplied):
            return False
        now = _time.monotonic()
        for stale in [t for t, exp in stream_tickets.items() if exp < now]:
            stream_tickets.pop(stale, None)
        return stream_tickets.pop(supplied, 0.0) >= now

    def _authenticated(request: Request) -> bool:
        if not token:
            return True
        supplied = request.headers.get("x-api-key", "")
        if hmac.compare_digest(supplied, token):
            return True
        cookie = request.cookies.get(SESSION_COOKIE, "")
        if bool(cookie) and _session_valid(cookie):
            return True
        return (request.url.path == "/api/stream"
                and _consume_stream_ticket(request))

    if not token:
        import logging

        logging.getLogger(__name__).warning(
            "dashboard auth DISABLED (no PRO_DASHBOARD_TOKEN) — dev/testing "
            "only; set the token before any non-loopback exposure"
        )
    if token:
        @app.middleware("http")
        async def require_api_key(request: Request, call_next):
            path = request.url.path
            # only /api/* carries data; the static shell and /healthz are
            # open. /api/session mints the cookie; /api/auth/config carries
            # no data (it tells the login screen which UI to render).
            if (not path.startswith("/api")
                    or path in ("/api/session", "/api/auth/config")):
                return await call_next(request)
            if _authenticated(request):
                return await call_next(request)
            return JSONResponse({"detail": "missing or invalid X-API-Key"},
                                status_code=401)

    if os.environ.get("PRO_DASHBOARD_DEV") == "1":
        # added after the auth middleware => wraps it, so 401s carry CORS
        # headers and the Vite dev origin can react to them
        from fastapi.middleware.cors import CORSMiddleware

        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["X-API-Key", "Content-Type", "Last-Event-ID"],
        )

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/health/live")
    def health_live() -> JSONResponse:
        # aggregate liveness for uptime monitors, the loop's entry gate,
        # and the dead-man switch. 503 when degraded so external monitors
        # treat degraded-while-armed as down (go-live Phase 5).
        from tradingagents.pro.health import live_health

        report = live_health(state, state.arming).as_dict()
        return JSONResponse(report, status_code=200 if report["ok"] else 503)

    @app.get("/metrics")
    def metrics() -> Response:
        # Prometheus scrape target; open like /healthz (no payload data,
        # counters only). Empty until a service loop attaches a registry.
        from fastapi.responses import PlainTextResponse

        rendered = state.metrics.render_prometheus() if state.metrics else ""
        return PlainTextResponse(rendered, media_type="text/plain; version=0.0.4")

    @app.get("/api/auth/config")
    def auth_config() -> dict:
        # open by design: no data, just which login UI the SPA should render
        # and where the EventSource should connect (null = same origin)
        return {
            "auth_required": bool(token),
            "google": google_enabled,
            "firebase": firebase_web_config if google_enabled else None,
            "stream_url": stream_direct_url if stream_direct else None,
        }

    @app.get("/api/stream/ticket")
    def stream_ticket() -> dict:
        # auth-gated by the middleware like every /api route: only an
        # established session (cookie through Hosting) can mint one
        import time as _time

        if not stream_direct:
            raise HTTPException(status_code=404,
                                detail="direct stream not configured")
        ticket = secrets.token_urlsafe(32)
        stream_tickets[ticket] = _time.monotonic() + STREAM_TICKET_TTL
        return {"ticket": ticket}

    def _google_identity(request: Request) -> str:
        """Validate the Authorization: Bearer Firebase ID token; returns the
        allowlisted email or raises HTTPException (401 invalid, 403 not
        allowed). Only called when google_enabled."""
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401,
                                detail="missing or invalid X-API-Key")
        try:
            claims = _verify_firebase_token(
                auth_header.removeprefix("Bearer ").strip(), firebase_project)
        except Exception:
            raise HTTPException(status_code=401,
                                detail="invalid or expired Google sign-in "
                                       "token") from None
        email = str(claims.get("email", "")).lower()
        if not claims.get("email_verified") or not email:
            raise HTTPException(status_code=401,
                                detail="Google account email not verified")
        if email not in allowed_emails:
            raise HTTPException(status_code=403,
                                detail="this Google account is not authorized")
        return email

    @app.post("/api/session")
    def create_session(request: Request, response: Response) -> dict:
        identity = None
        if token:
            supplied = request.headers.get("x-api-key", "")
            authed = hmac.compare_digest(supplied, token)
            if not authed:
                # an existing valid session JWT re-establishes on boot — a
                # Google user's page reload carries ONLY the cookie (no
                # header, no fresh ID token) and must not bounce to the
                # login screen. The signed `sub` claim restores identity;
                # re-minting below gives a sliding TTL.
                claims = _session_claims(
                    request.cookies.get(SESSION_COOKIE, ""))
                if claims is not None:
                    authed = True
                    if claims.get("sub") not in (None, "api-token"):
                        identity = str(claims["sub"])
            if not authed:
                if not google_enabled:
                    raise HTTPException(status_code=401,
                                        detail="missing or invalid X-API-Key")
                identity = _google_identity(request)  # raises 401/403
            # max_age: without it the browser drops the cookie on quit —
            # combined with the stateless JWT, sign-in survives browser
            # restarts, server redeploys, and scale-to-zero for the TTL
            response.set_cookie(SESSION_COOKIE, _mint_session(identity),
                                httponly=True, samesite="strict", path="/",
                                max_age=SESSION_TTL_SECONDS)
        return {"authenticated": True, "auth_required": bool(token),
                "identity": identity}

    @app.get("/api/stream")
    async def stream(request: Request) -> StreamingResponse:
        state.broadcaster.ensure_loop()
        raw = (request.headers.get("last-event-id")
               or request.query_params.get("last_event_id") or "")
        last_id = int(raw) if raw.isdigit() else None
        raw_max = request.query_params.get("max_events") or ""
        max_events = int(raw_max) if raw_max.isdigit() else None

        async def frames():
            # max_events bounds the stream (curl debugging, tests);
            # browsers omit it and hold the connection open
            delivered = 0
            agen = state.broadcaster.subscribe(last_id)
            try:
                async for frame in agen:
                    yield frame
                    if frame.startswith("id:"):  # real events only, not heartbeats
                        delivered += 1
                        if max_events is not None and delivered >= max_events:
                            return
            finally:
                await agen.aclose()

        headers = {"Cache-Control": "no-cache",
                   "X-Accel-Buffering": "no"}  # nginx: do not buffer SSE
        # direct-SSE is cross-origin from the Hosting site; EventSource GETs
        # are CORS "simple requests" (no preflight) but the response must
        # name the allowed origin. Ticket auth means no credentials header.
        if stream_direct and (request.headers.get("origin", "").rstrip("/")
                              == stream_allowed_origin):
            headers["Access-Control-Allow-Origin"] = stream_allowed_origin
        return StreamingResponse(
            frames(),
            media_type="text/event-stream",
            headers=headers,
        )

    def _legacy_html() -> str:
        return (
            resources.files("tradingagents.pro.dashboard")
            .joinpath("templates", "dashboard.html")
            .read_text(encoding="utf-8")
        )

    static_root = resources.files("tradingagents.pro.dashboard") / "static"
    spa_index = static_root / "index.html"
    try:
        has_spa = spa_index.is_file()
    except Exception:
        has_spa = False

    if has_spa:
        import os as _os

        from fastapi.staticfiles import StaticFiles

        assets_dir = _os.fspath(static_root / "assets")
        if _os.path.isdir(assets_dir):
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        if has_spa:
            return HTMLResponse(spa_index.read_text(encoding="utf-8"),
                                headers={"Cache-Control": "no-cache"})
        return HTMLResponse(_legacy_html())

    @app.get("/legacy", response_class=HTMLResponse)
    def legacy() -> str:
        return _legacy_html()

    @app.get("/api/symbols")
    def symbols() -> list[dict]:
        return state.marketdata.symbols()

    def _parse_timeframe(value: str):
        from tradingagents.contracts import Timeframe

        try:
            return Timeframe(value)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"unknown timeframe {value!r}; use one of "
                       f"{[t.value for t in Timeframe]}",
            ) from None

    def _fetch_bars(symbol: str, timeframe: str, limit: int):
        from tradingagents.dataflows.errors import (
            NoMarketDataError,
            VendorRateLimitError,
        )

        tf = _parse_timeframe(timeframe)
        try:
            return state.marketdata.get_bars(symbol, tf, limit)
        except md.UnknownSymbolError:
            raise HTTPException(status_code=404,
                                detail=f"unknown symbol {symbol!r}") from None
        except md.UnsupportedTimeframeError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        except VendorRateLimitError as exc:
            raise HTTPException(status_code=503, detail=str(exc),
                                headers={"Retry-After": "30"}) from None
        except NoMarketDataError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        except Exception as exc:  # vendor unreachable / network egress blocked
            raise HTTPException(
                status_code=503,
                detail=f"market data vendor unreachable: {type(exc).__name__}",
                headers={"Retry-After": "60"},
            ) from None

    @app.get("/api/bars")
    def bars(symbol: str, timeframe: str = "1d",
             limit: int = md.DEFAULT_LIMIT) -> list[dict]:
        return md.bars_view(_fetch_bars(symbol, timeframe, limit))

    @app.get("/api/bars/indicators")
    def bar_indicators(symbol: str, timeframe: str = "1d",
                       names: str = "", limit: int = md.DEFAULT_LIMIT) -> dict:
        from tradingagents.pro.ingestion.indicators import DEFAULT_INDICATOR_NAMES

        requested = tuple(n for n in names.split(",") if n) or DEFAULT_INDICATOR_NAMES
        fetched = _fetch_bars(symbol, timeframe, limit)
        try:
            return md.indicator_series_view(fetched, requested)
        except ValueError as exc:  # unknown indicator names
            raise HTTPException(status_code=422, detail=str(exc)) from None

    @app.get("/api/bars/volume-profile")
    def bars_volume_profile(symbol: str, timeframe: str = "1d",
                            limit: int = md.DEFAULT_LIMIT,
                            bins: int = 24) -> dict:
        """Fixed-range volume profile over the served bar window (review
        P2.4) — deterministic server math; the chart renders, never
        computes."""
        from tradingagents.pro.ingestion.profile import volume_profile

        fetched = _fetch_bars(symbol, timeframe, limit)
        try:
            return volume_profile(fetched, bins=bins)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None

    @app.get("/api/overview")
    def overview() -> dict:
        return service.market_overview(state.latest_run())

    _regime_cache: dict = {"at": 0.0, "payload": None}

    @app.get("/api/regime")
    def regime() -> dict:
        """Per-symbol deterministic regime (trader review G3) — the same
        classify_regime the pipeline records, computed over daily bars for
        every dashboard symbol so the strip never shows one symbol's
        regime on another's screen. Never an LLM."""
        import time as _time

        from tradingagents.pro.analytics.features import classify_regime
        from tradingagents.pro.ingestion.sessions import current_session

        now = _time.monotonic()
        if _regime_cache["payload"] is not None and now - _regime_cache["at"] < 300:
            return _regime_cache["payload"]
        from datetime import datetime, timezone

        symbols: dict[str, dict] = {}
        for sym in sorted(state.marketdata.registry):
            try:
                bars = state.marketdata.get_bars(sym, "1d", limit=60)
                value = classify_regime(bars).value if len(bars) >= 3 else None
            except Exception:
                value = None  # degraded vendor -> honest null, not a guess
            symbols[sym] = {"regime": value}
        as_of = datetime.now(timezone.utc)
        payload = {
            "symbols": symbols,
            "session": current_session(as_of).value,
            "as_of": as_of.isoformat(),
        }
        _regime_cache.update(at=now, payload=payload)
        return payload

    @app.get("/api/runs")
    def runs() -> list[dict]:
        return [
            {
                "run_id": run.run_id,
                "started_at": run.started_at.isoformat(),
                "symbol": run.symbol,
                "action": run.recommendation.action.value if run.recommendation else None,
                "rejected_at": run.rejection and run.rejection.get("stage"),
                "timeframe": run.timeframe,
            }
            for run in state.runs
        ]

    def _run_or_404(run_id: str) -> RunRecord:
        for run in state.runs:
            if run.run_id == run_id:
                return run
        raise HTTPException(status_code=404, detail=f"no run {run_id}")

    @app.get("/api/runs/{run_id}/timeline")
    def timeline(run_id: str) -> dict:
        return service.debate_timeline(_run_or_404(run_id))

    @app.get("/api/runs/{run_id}/evidence")
    def evidence(run_id: str) -> dict:
        return service.evidence_panels(_run_or_404(run_id))

    def _ticket_view(run: RunRecord | None) -> dict:
        if run is None:
            return service.recommendation_view(None)
        reflection = run.state.get("reflection") or {}
        view = service.recommendation_view(
            run.recommendation,
            invalidation=reflection.get("invalidation"),
            rejection=run.rejection,
        )
        # let per-symbol/per-run consumers link back without /api/overview
        view.setdefault("symbol", run.symbol)
        view["run_id"] = run.run_id
        view["run_started_at"] = run.started_at.isoformat()
        view["timeframe"] = run.timeframe
        return view

    # async on purpose (review R2.7): these are pure in-memory reads, yet as
    # sync defs they shared the threadpool with vendor-bound handlers
    # (intel/bars/calendar) and were observed queuing >30s behind them.
    # On the event loop they cannot be starved.
    @app.get("/api/recommendation/latest")
    async def latest_recommendation(symbol: str | None = None) -> dict:
        run = state.latest_run_for(symbol) if symbol else state.latest_run()
        return _ticket_view(run)

    @app.get("/api/runs/{run_id}/recommendation")
    async def run_recommendation(run_id: str) -> dict:
        return _ticket_view(_run_or_404(run_id))

    @app.get("/api/status")
    def status() -> dict:
        return service.system_status(state.router, state.equity, state.arming,
                                     ticks=state.ticks, marketdata=state.marketdata)

    @app.post("/api/flatten")
    async def flatten(request: Request) -> JSONResponse:
        """Emergency flatten — the ONE sanctioned dashboard->execution
        write. Behind auth (the /api middleware) plus a typed-confirmation
        body echoing the exact phrase the UI generated."""
        if state.router is None:
            raise HTTPException(status_code=503,
                                detail="no execution router attached")
        body = await request.json()
        if body.get("confirm") != "FLATTEN":
            raise HTTPException(
                status_code=422,
                detail="type FLATTEN to confirm the emergency flatten")
        from tradingagents.pro.flatten import emergency_flatten

        summary = emergency_flatten(
            state.router, arming=state.arming, operator="dashboard",
            alerts=getattr(state, "alerts", None))
        return JSONResponse({"status": "flattened", **summary})

    @app.get("/api/alerts")
    def alerts() -> dict:
        return service.alert_feed(state.runs)

    @app.post("/api/pipeline/run")
    async def run_pipeline(request: Request) -> JSONResponse:
        import threading as _threading

        body = await request.json()
        symbol = body.get("symbol")
        timeframe = body.get("timeframe")
        trigger = state.trigger
        if trigger is None:
            raise HTTPException(
                status_code=503,
                detail="no pipeline service attached (monitor mode) — "
                       "run via the service container or pro_live_terminal",
            )
        if symbol not in trigger.SYMBOLS or timeframe not in trigger.TIMEFRAMES:
            raise HTTPException(
                status_code=422,
                detail=f"symbol must be one of {list(trigger.SYMBOLS)} and "
                       f"timeframe one of {list(trigger.TIMEFRAMES)}",
            )
        if trigger.busy():
            raise HTTPException(status_code=409,
                                detail="a pipeline run is already in progress")

        def work():
            import logging as _logging

            try:
                trigger.run(symbol, timeframe)
            except Exception:
                _logging.getLogger(__name__).exception("on-demand run failed")

        _threading.Thread(target=work, name="on-demand-run", daemon=True).start()
        return JSONResponse({"status": "started", "symbol": symbol,
                             "timeframe": timeframe}, status_code=202)

    @app.get("/api/prefs")
    def get_prefs() -> dict:
        return state.prefs.get_prefs()

    @app.put("/api/prefs")
    async def put_prefs(request: Request) -> dict:
        body = await request.body()
        if len(body) > 256 * 1024:
            raise HTTPException(status_code=413, detail="prefs document too large")
        import json as _json

        from pydantic import ValidationError

        try:
            return state.prefs.put_prefs(_json.loads(body))
        except _json.JSONDecodeError as exc:
            raise HTTPException(status_code=422, detail=f"invalid JSON: {exc}") from None
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors()) from None

    @app.get("/api/watchlists")
    def watchlists() -> list[dict]:
        return state.prefs.watchlists()

    @app.post("/api/watchlists")
    async def upsert_watchlist(request: Request) -> dict:
        from pydantic import ValidationError

        try:
            return state.prefs.upsert_watchlist(await request.json())
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors()) from None

    @app.delete("/api/watchlists/{name}")
    def delete_watchlist(name: str) -> dict:
        if not state.prefs.delete_watchlist(name):
            raise HTTPException(status_code=404, detail=f"no watchlist {name!r}")
        return {"deleted": name}

    @app.get("/api/price-alerts")
    def price_alerts() -> list[dict]:
        return state.prefs.price_alerts()

    @app.post("/api/price-alerts")
    async def create_price_alert(request: Request) -> dict:
        data = await request.json()
        symbol = data.get("symbol")
        if symbol not in state.marketdata.registry:
            raise HTTPException(
                status_code=422,
                detail=f"unknown symbol {symbol!r}; "
                       f"supported: {sorted(state.marketdata.registry)}")
        try:
            return state.prefs.add_price_alert(data)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        except Exception as exc:  # pydantic validation
            raise HTTPException(status_code=422, detail=str(exc)) from None

    @app.delete("/api/price-alerts/{alert_id}")
    def delete_price_alert(alert_id: str) -> dict:
        if not state.prefs.delete_price_alert(alert_id):
            raise HTTPException(status_code=404, detail=f"no alert {alert_id}")
        return {"deleted": alert_id}

    @app.get("/api/notifications")
    def notifications(unread: int = 0) -> dict:
        notes = state.prefs.notifications(unread_only=bool(unread))
        return {"notifications": notes,
                "unread": sum(1 for n in notes if not n["read"])}

    @app.post("/api/notifications/read")
    async def mark_notifications_read(request: Request) -> dict:
        body = await request.json() if int(request.headers.get("content-length") or 0) else {}
        return {"marked": state.prefs.mark_read(body.get("ids"))}

    @app.get("/api/journal")
    def journal() -> dict:
        return service.trade_journal(state.memory)

    @app.get("/api/backtest")
    def backtest() -> dict:
        return service.backtest_view(state.backtest, state.monte_carlo)

    @app.get("/api/memory")
    def memory_view() -> dict:
        return service.memory_insights(state.memory)

    @app.get("/api/intel")
    def intel() -> dict:
        return state.intel.snapshot()

    @app.get("/api/intel/correlations")
    def intel_correlations(window: int = 30) -> dict:
        return state.intel.correlations(state.marketdata, window)

    @app.get("/api/calendar")
    def calendar(days: int = 30) -> dict:
        return state.intel.calendar(days)

    @app.get("/api/export/journal.csv")
    def export_journal_csv() -> StreamingResponse:
        import csv
        import io
        from datetime import date

        journal = service.trade_journal(state.memory)

        def rows():
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow(["symbol", "action", "regime", "pnl", "won",
                             "closed_at", "mode", "commission",
                             "venue_order_id", "fill_price", "entry_price"])
            yield buffer.getvalue()
            for entry in journal["entries"]:
                buffer.seek(0)
                buffer.truncate(0)
                writer.writerow([entry["symbol"], entry["action"],
                                 entry["regime"], entry["pnl"], entry["won"],
                                 entry["closed_at"], entry.get("mode"),
                                 entry.get("commission"),
                                 entry.get("venue_order_id"),
                                 entry.get("fill_price"),
                                 entry.get("entry_price")])
                yield buffer.getvalue()

        return StreamingResponse(
            rows(), media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition":
                     f'attachment; filename="journal-{date.today():%Y%m%d}.csv"'},
        )

    @app.get("/api/export/report.json")
    def export_report() -> dict:
        import importlib.metadata

        run = state.latest_run()
        reflection = (run.state.get("reflection") or {}) if run else {}
        try:
            app_version = importlib.metadata.version("tradingagents")
        except importlib.metadata.PackageNotFoundError:
            app_version = "dev"
        from tradingagents.contracts import utc_now

        return {
            "generated_at": utc_now().isoformat(),
            "app_version": app_version,
            "overview": service.market_overview(run),
            "recommendation": service.recommendation_view(
                run.recommendation if run else None,
                invalidation=reflection.get("invalidation"),
                rejection=run.rejection if run else None,
            ),
            "status": service.system_status(state.router, state.equity),
            "journal": service.trade_journal(state.memory),
            "backtest": service.backtest_view(state.backtest, state.monte_carlo),
            "agents": service.agent_performance(state.runs, state.memory),
            "memory": service.memory_insights(state.memory),
            "alerts": service.alert_feed(state.runs),
        }

    @app.get("/api/agents")
    def agents() -> dict:
        return service.agent_performance(state.runs, state.memory)

    # SPA fallback: root-level build files (sw.js, manifest, icons) are
    # served as files; client routes (/trade/..., /decisions/...) get
    # index.html; unknown /api paths still 404. Registered last.
    @app.get("/{path:path}", include_in_schema=False)
    def spa_fallback(path: str):
        import mimetypes

        from fastapi.responses import Response

        if path.startswith("api/") or path in ("api", "healthz", "metrics"):
            raise HTTPException(status_code=404, detail=f"no route /{path}")
        if has_spa and path and ".." not in path:
            candidate = static_root / path
            try:
                is_file = candidate.is_file()
            except Exception:
                is_file = False
            if is_file:
                media_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
                cache = ("no-cache" if path in ("sw.js", "index.html")
                         else "public, max-age=86400")
                return Response(candidate.read_bytes(), media_type=media_type,
                                headers={"Cache-Control": cache})
        if has_spa:
            return HTMLResponse(spa_index.read_text(encoding="utf-8"),
                                headers={"Cache-Control": "no-cache"})
        return HTMLResponse(_legacy_html())

    return app


def create_default_app():
    """uvicorn --factory entry point with empty state."""
    return create_app()
