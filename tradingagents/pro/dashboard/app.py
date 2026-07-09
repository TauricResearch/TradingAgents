"""FastAPI application for the Pro dashboard.

Requires the ``dashboard`` extra (``pip install "tradingagents[dashboard]"``).
The app is a thin shell: every endpoint delegates to the tested view-model
functions in service.py; the SPA (or the legacy single page) renders them.

Auth model: all ``/api/*`` routes require ``X-API-Key`` when a token is
configured. ``POST /api/session`` exchanges the key for an HttpOnly cookie
so browser-native transports that cannot set headers (EventSource,
``<a download>``) still authenticate. Static shell and ``/healthz`` are
open — they contain no data.

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
from tradingagents.pro.memory import ProMemory

SESSION_COOKIE = "pro_session"


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
    prefs: PrefsStore = field(default_factory=PrefsStore)
    intel: IntelService = field(default_factory=IntelService)
    trigger = None            # PipelineTrigger, when a service loop is attached

    @property
    def runs(self) -> list[RunRecord]:
        return self.recorder.runs

    def latest_run(self) -> RunRecord | None:
        return self.runs[-1] if self.runs else None


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
    sessions: set[str] = set()  # in-process; restart = re-auth via header

    @asynccontextmanager
    async def lifespan(app):
        state.broadcaster.bind_loop(asyncio.get_running_loop())
        pollers = []
        try:
            from tradingagents.pro.dashboard.ticker import QuoteTickPoller

            # one poller per live symbol whose vendor supports quotes;
            # registry access runs the vendor probes (logged) exactly once
            for spec in state.marketdata.registry.values():
                if spec.live and spec.source in ("delta_exchange", "oanda_gold"):
                    poller = QuoteTickPoller(
                        spec.feed_factory(), state.broadcaster,
                        symbol=spec.vendor_symbol, display_symbol=spec.symbol,
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

    def _authenticated(request: Request) -> bool:
        if not token:
            return True
        supplied = request.headers.get("x-api-key", "")
        if hmac.compare_digest(supplied, token):
            return True
        cookie = request.cookies.get(SESSION_COOKIE, "")
        return bool(cookie) and cookie in sessions

    if token:
        @app.middleware("http")
        async def require_api_key(request: Request, call_next):
            path = request.url.path
            # only /api/* carries data; the static shell and /healthz are open
            if not path.startswith("/api") or path == "/api/session":
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

    @app.post("/api/session")
    def create_session(request: Request, response: Response) -> dict:
        if token:
            supplied = request.headers.get("x-api-key", "")
            if not hmac.compare_digest(supplied, token):
                raise HTTPException(status_code=401,
                                    detail="missing or invalid X-API-Key")
            session_id = secrets.token_urlsafe(32)
            sessions.add(session_id)
            response.set_cookie(SESSION_COOKIE, session_id, httponly=True,
                                samesite="strict", path="/")
        return {"authenticated": True, "auth_required": bool(token)}

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

        return StreamingResponse(
            frames(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache",
                     "X-Accel-Buffering": "no"},  # nginx: do not buffer SSE
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

    @app.get("/api/overview")
    def overview() -> dict:
        return service.market_overview(state.latest_run())

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

    @app.get("/api/recommendation/latest")
    def latest_recommendation() -> dict:
        run = state.latest_run()
        if run is None:
            return service.recommendation_view(None)
        reflection = run.state.get("reflection") or {}
        return service.recommendation_view(
            run.recommendation,
            invalidation=reflection.get("invalidation"),
            rejection=run.rejection,
        )

    @app.get("/api/status")
    def status() -> dict:
        return service.system_status(state.router, state.equity)

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
                             "closed_at"])
            yield buffer.getvalue()
            for entry in journal["entries"]:
                buffer.seek(0)
                buffer.truncate(0)
                writer.writerow([entry["symbol"], entry["action"],
                                 entry["regime"], entry["pnl"], entry["won"],
                                 entry["closed_at"]])
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
