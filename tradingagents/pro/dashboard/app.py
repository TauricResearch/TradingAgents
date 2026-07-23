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
from tradingagents.pro.dashboard.backtest_store import BacktestRunStore
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
    backtest_runs: BacktestRunStore = field(default_factory=BacktestRunStore)
    backtest_job = None      # BacktestJob, while an interactive run is in flight
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

    def _fetch_bars(symbol: str, timeframe: str, limit: int,
                    end: int | None = None):
        from datetime import datetime, timezone

        from tradingagents.dataflows.errors import (
            NoMarketDataError,
            VendorRateLimitError,
        )

        tf = _parse_timeframe(timeframe)
        end_dt = (datetime.fromtimestamp(end, tz=timezone.utc)
                  if end is not None else None)
        try:
            return state.marketdata.get_bars(symbol, tf, limit, end=end_dt)
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
             limit: int = md.DEFAULT_LIMIT,
             end: int | None = None) -> list[dict]:
        """``end`` (epoch seconds, exclusive) pages history backward — the
        chart's load-more. Omitted = the latest window (unchanged)."""
        return md.bars_view(_fetch_bars(symbol, timeframe, limit, end))

    @app.get("/api/chart/annotations")
    async def chart_annotations_route(symbol: str) -> dict:
        """The AI's record for one symbol, chart-paintable (chart Phase 1).
        Async on purpose: pure in-memory read — never queued behind
        vendor-bound threadpool handlers (the R2.7 lesson)."""
        import os

        from tradingagents.pro.dashboard.annotations import chart_annotations

        known = {s["symbol"] for s in state.marketdata.symbols()}
        if symbol not in known:
            raise HTTPException(status_code=404,
                                detail=f"unknown symbol {symbol!r}")
        cadence = float(os.environ.get("PRO_LOOP_INTERVAL_SECONDS", "3600"))
        return chart_annotations(state.runs, state.memory, symbol,
                                 cadence_seconds=cadence)

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
                "trigger": run.trigger,
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
        # empirical p(win) from the system's own scored record (lived +
        # retro outcomes); None below the sample floor — never invented
        if run.recommendation is not None:
            view["p_win"] = service.estimate_p_win(
                state.memory, run.recommendation.confidence)
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

    def _ask_prep(run_id: str, body: dict):
        """Shared validation + prompt inputs for the ask endpoints. Returns
        (run, llm, question, supporting, counters, invalidation)."""
        from tradingagents.pro.pipeline.nodes import _all_evidence
        from tradingagents.pro.pipeline.qa import MAX_QUESTION_CHARS

        run = _run_or_404(run_id)
        service_obj = getattr(state.trigger, "service", None)
        llm = getattr(service_obj, "llm", None)
        if llm is None:
            raise HTTPException(
                status_code=503,
                detail="ask is unavailable in monitor mode (no model attached)")
        question = str(body.get("question", "")).strip()
        if not question:
            raise HTTPException(status_code=422, detail="question is required")
        if len(question) > MAX_QUESTION_CHARS:
            raise HTTPException(
                status_code=422,
                detail=f"question exceeds {MAX_QUESTION_CHARS} characters")
        rec = run.recommendation
        if rec is not None:
            supporting = list(rec.evidence)
            counters = list(rec.counterarguments)
        else:  # rejected / HOLD: pull whatever evidence the run gathered
            try:
                supporting = _all_evidence(run.state)
            except Exception:
                supporting = []
            counters = []
        invalidation = (run.state.get("reflection") or {}).get("invalidation")
        return run, llm, question, supporting, counters, invalidation

    @app.post("/api/runs/{run_id}/ask")
    async def ask_run(run_id: str, request: Request) -> dict:
        """Grounded Q&A over ONE run's record (evidence/debate/verdict).
        Answers only from that record with agent-id citations; refuses to
        reach beyond it. Needs the pipeline LLM (the loop's own bundle)."""
        from tradingagents.pro.models import ModelBundle
        from tradingagents.pro.pipeline.nodes import _debate_block
        from tradingagents.pro.pipeline.qa import EvidenceAnswer, build_qa_prompt

        run, llm, question, supporting, counters, invalidation = _ask_prep(
            run_id, await request.json())
        prompt = build_qa_prompt(
            question, symbol=run.symbol, recommendation=run.recommendation,
            supporting=supporting, counterarguments=counters,
            debate_block=_debate_block(run.debate), invalidation=invalidation)
        bundle = ModelBundle.coerce(llm)
        try:
            answer = await asyncio.to_thread(
                bundle.deep.with_structured_output(EvidenceAnswer).invoke, prompt)
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"model call failed: {type(exc).__name__}") from None
        if answer is None:
            raise HTTPException(status_code=502, detail="model returned nothing")
        return {
            "run_id": run.run_id,
            "answerable": answer.answerable,
            "answer": answer.answer,
            "cited_agent_ids": list(answer.cited_agent_ids),
        }

    @app.post("/api/runs/{run_id}/ask/stream")
    async def ask_run_stream(run_id: str, request: Request) -> StreamingResponse:
        """Streaming grounded Q&A (PB.2): same record-only discipline, but
        the answer prose streams token-by-token (<5s to first token vs the
        structured endpoint's ~30s wait), ending with a 'SOURCES:' line the
        client splits into citation tags. Falls back to /ask on the client
        if the model can't stream."""
        from tradingagents.pro.models import ModelBundle
        from tradingagents.pro.pipeline.nodes import _debate_block
        from tradingagents.pro.pipeline.qa import build_qa_stream_prompt

        run, llm, question, supporting, counters, invalidation = _ask_prep(
            run_id, await request.json())
        prompt = build_qa_stream_prompt(
            question, symbol=run.symbol, recommendation=run.recommendation,
            supporting=supporting, counterarguments=counters,
            debate_block=_debate_block(run.debate), invalidation=invalidation)
        bundle = ModelBundle.coerce(llm)

        def generate():
            try:
                for chunk in bundle.deep.stream(prompt):
                    text = getattr(chunk, "content", None)
                    if text:
                        yield text if isinstance(text, str) else str(text)
            except Exception as exc:  # surface as an in-band note, never 500
                yield f"\n[stream interrupted: {type(exc).__name__}]"

        return StreamingResponse(generate(), media_type="text/plain")

    @app.get("/api/status")
    def status() -> dict:
        return service.system_status(state.router, state.equity, state.arming,
                                     ticks=state.ticks, marketdata=state.marketdata,
                                     memory=state.memory)

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

    @app.get("/api/portfolio/stats")
    def portfolio_stats() -> dict:
        """Live-book analytics (trader review): closed-trade performance
        + aggregate open exposure — the real record, not the backtest."""
        base = (state.router.breaker.equity_base
                if state.router is not None
                and getattr(state.router, "breaker", None) is not None
                else 100_000.0)
        perf = service.journal_performance(state.memory, starting_equity=base)
        positions, _ = service.open_positions_view(
            state.router, state.equity, ticks=state.ticks,
            marketdata=state.marketdata,
            memory=state.memory) if state.router is not None else ([], None)
        max_open = (state.router.limits.max_open_positions
                    if state.router is not None else 3)
        perf["exposure"] = service.portfolio_exposure(
            positions, state.equity, max_open)
        return perf

    @app.get("/api/scanner")
    def scanner() -> dict:
        """Deterministic universe scan (trader review: 'today's best
        opportunity immediately'): the pipeline's zero-LLM prepare-stage
        features across every tradeable symbol, ranked. Running the full
        agent debate stays a deliberate, priced action."""
        from tradingagents.contracts import utc_now
        from tradingagents.pro.analytics.features import (
            classify_regime,
            close_zscore,
            realized_volatility,
            trend_slope,
        )

        rows = []
        for spec in state.marketdata.registry.values():
            if not spec.tradeable:
                continue
            try:
                tf = "1h" if any(t.value == "1h" for t in spec.timeframes) else "1d"
                bars = state.marketdata.get_bars(spec.symbol, tf, limit=120)
                if len(bars) < 60:
                    continue
                regime = classify_regime(bars)
                slope, r2 = trend_slope(bars)
                zscore = close_zscore(bars)
                vol = realized_volatility(bars)
                # setup score: stretched price (|z|) in a directional regime
                # scores highest; pure chop scores lowest. Deterministic and
                # explainable — not a prediction.
                regime_weight = {
                    "trending_up": 1.0, "trending_down": 1.0,
                    "high_volatility": 0.8, "crisis": 0.8,
                    "low_volatility": 0.5, "ranging": 0.4,
                }.get(regime.value, 0.3)
                score = round((abs(zscore) + abs(slope) * 50) * regime_weight, 2)
                rows.append({
                    "symbol": spec.symbol,
                    "timeframe": tf,
                    "regime": regime.value,
                    "trend_slope": slope,
                    "trend_r2": r2,
                    "zscore": zscore,
                    "realized_vol": vol,
                    "last_close": bars[-1].close,
                    "score": score,
                })
            except Exception:  # one degraded vendor never blanks the scan
                continue
        rows.sort(key=lambda r: r["score"], reverse=True)
        return {"rows": rows, "as_of": utc_now().isoformat()}

    @app.post("/api/calibration/backfill")
    def calibration_backfill() -> dict:
        """Retro-score stored REAL runs against subsequent bars so the
        calibration chart accrues (trader review: 'twenty scored trades').
        Idempotent; provenance-tagged; excluded from the blotter."""
        from tradingagents.contracts import Timeframe
        from tradingagents.pro.analytics.retro import backfill_outcomes

        def bars_for(run):
            tf = Timeframe(run.timeframe or "1h")
            bars = state.marketdata.get_bars(run.symbol, tf.value, limit=1000)
            return [b for b in bars if b.start > run.started_at]

        service_obj = getattr(state.trigger, "service", None)
        open_rec_ids = {
            pos.recommendation.id
            for pos in getattr(service_obj, "open_positions", {}).values()
            if getattr(pos, "recommendation", None) is not None
        }
        result = backfill_outcomes(state.runs, state.memory, bars_for,
                                   open_rec_ids=open_rec_ids)
        return result

    @app.get("/api/risk/budget")
    def risk_budget() -> dict:
        budget = service.risk_budget(state.router)
        if budget.get("attached"):
            trigger = state.trigger
            budget["orders_today"] = getattr(
                getattr(trigger, "service", None), "_orders_today", None)
        return budget

    @app.get("/api/backtest")
    def backtest() -> dict:
        return service.backtest_view(state.backtest, state.monte_carlo)

    import threading as _bt_threading

    _backtest_lock = _bt_threading.Lock()

    @app.post("/api/backtest/run")
    async def run_backtest(request: Request) -> JSONResponse:
        """Start an interactive backtest as a background job (returns 202 +
        job_id). Progress + trades stream over /api/stream (backtest_progress
        / backtest_trade / backtest_done). Deterministic by default (scripted
        no-cost LLM — mechanics, not model skill); ``use_llm`` runs the real
        pipeline from .env keys (costs money, capped, requires confirm_cost).
        Uses an ISOLATED memory so simulations never touch the live record."""
        from pydantic import ValidationError

        from tradingagents.pro.dashboard import backtest_job as btjob

        body = await request.json()
        try:
            req = btjob.BacktestRunRequest.model_validate(body)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors()) from exc
        params = req.model_dump()
        # validate + cost-gate before taking the lock or spawning a thread
        try:
            btjob.resolve_request(state.marketdata, params)
        except btjob._CostConfirmationRequired as exc:
            raise HTTPException(
                status_code=400,
                detail={"error": "cost_confirmation_required",
                        "estimate": exc.estimate},
            ) from exc
        except (ValueError, md.UnknownSymbolError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        if not _backtest_lock.acquire(blocking=False):
            raise HTTPException(status_code=409,
                                detail="a backtest is already running")
        job = btjob.new_job(params)
        state.backtest_job = job

        def work():
            try:
                btjob.run_job(state, job, params)
            finally:
                _backtest_lock.release()

        _bt_threading.Thread(target=work, name="backtest-run",
                             daemon=True).start()
        return JSONResponse({"job_id": job.id, "status": "started"},
                            status_code=202)

    @app.post("/api/backtest/cancel")
    def cancel_backtest() -> dict:
        """Stop the in-flight run; the partial (trades, equity, decisions so
        far) is saved to the run history labeled ``cancelled``."""
        job = state.backtest_job
        if job is None or job.status != "running":
            raise HTTPException(status_code=409, detail="no backtest running")
        job.cancel.set()
        return {"status": "cancelling", "job_id": job.id}

    @app.get("/api/backtest/job")
    def backtest_job_status() -> dict:
        job = state.backtest_job
        return job.snapshot() if job is not None else {"status": "idle"}

    @app.get("/api/backtest/strategies")
    def backtest_strategies() -> dict:
        """Registered strategies + their declared parameter schema (track T1),
        so the UI can render the strategy picker + param inputs dynamically."""
        from tradingagents.pro.backtest import list_strategies

        # pipeline_llm is job-built (needs the model bundle, not the registry)
        # so it is advertised alongside the registered rules_v1 with the same
        # declared parameter schema.
        infos = {s.id: s for s in list_strategies()}
        rules = infos.get("rules_v1")
        rules_params = rules.params if rules is not None else []
        return {"strategies": [
            {"id": "rules_v1",
             "description": rules.description if rules is not None else "",
             "params": rules_params},
            {"id": "pipeline_llm",
             "description": "Real multi-agent LLM pipeline on the operator's "
                            "model bundle — costs money, measures model skill. "
                            "Same risk geometry and gates as rules_v1.",
             "params": rules_params},
        ]}

    @app.get("/api/backtest/runs")
    def backtest_runs() -> dict:
        return {"runs": state.backtest_runs.list()}

    @app.get("/api/backtest/runs/{run_id}")
    def backtest_run(run_id: str) -> dict:
        record = state.backtest_runs.get(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail="unknown backtest run")
        return record

    @app.get("/api/backtest/runs/{run_id}/artifacts/{name}")
    def backtest_artifact(run_id: str, name: str):
        """Full-fidelity bulk data for one run (every equity point / trade /
        decision) — streamed from the per-run artifact files, never embedded
        in the record."""
        from fastapi.responses import FileResponse

        from tradingagents.pro.dashboard.backtest_artifacts import (
            ARTIFACT_NAMES,
            RunArtifacts,
        )
        if name not in ARTIFACT_NAMES:
            raise HTTPException(status_code=404, detail="unknown artifact")
        path = RunArtifacts(run_id).path(name)
        if not path.is_file():
            raise HTTPException(status_code=404, detail="artifact not found")
        return FileResponse(path, media_type="application/json")

    @app.delete("/api/backtest/runs/{run_id}")
    def delete_backtest_run(run_id: str) -> dict:
        from tradingagents.pro.dashboard.backtest_artifacts import RunArtifacts

        if not state.backtest_runs.delete(run_id):
            raise HTTPException(status_code=404, detail="unknown backtest run")
        RunArtifacts(run_id).delete()
        return {"status": "deleted", "id": run_id}

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
