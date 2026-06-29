"""FastAPI application factory for the TradingAgents dashboard."""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import threading
import time
import uuid
import zipfile
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from tradingagents.default_config import _ENV_OVERRIDES, DEFAULT_CONFIG
from web.server.chat_router import router as chat_router
from web.server.ticker_agent import orchestrator
from web.server.ticker_agent.router import router as ticker_agent_router

from . import (
    events,
    indicators,
    log_publisher as lp_module,
    queries,
    runner,
    settings as settings_mod,
    storage,
)
from .auth import read_session, read_session_from_ws, router as auth_router

log = logging.getLogger(__name__)


class NotifierIn(BaseModel):
    enabled: bool | None = None
    bot_token: str | None = None
    chat_id: str | None = None


class NotifierOut(BaseModel):
    enabled: bool
    bot_token: str | None
    chat_id: str | None


def _get_notifier():
    """Build a TelegramNotifier from stored config, or None if not configured."""
    try:
        cfg = storage.read_notifier_config()
        if not cfg.get("enabled"):
            return None
        token = cfg.get("bot_token")
        chat_id = cfg.get("chat_id")
        if not token or not chat_id:
            return None
        return _TelegramNotifierProxy(token, chat_id)
    except Exception:
        log.exception("Failed to create notifier")
        return None


class _TelegramNotifierProxy:
    """Thin async wrapper around the sync Bot.send_message for use in sync endpoints."""

    def __init__(self, token: str, chat_id: str | int) -> None:
        from telegram import Bot

        self._token = token
        self._chat_id = str(chat_id)
        self._bot = Bot(token=self._token)

    async def send_results(self, results) -> None:
        from telegram.error import Forbidden, InvalidToken

        from web.server.notifier import build_results_message

        try:
            await self._bot.send_message(
                chat_id=self._chat_id,
                text=build_results_message(results),
                parse_mode="HTML",
            )
        except Forbidden as exc:
            log.error("Telegram Forbidden: %s", exc)
        except InvalidToken as exc:
            log.error("Telegram InvalidToken: %s", exc)

    async def send_raw(self, text: str) -> None:
        from telegram.error import Forbidden, InvalidToken

        try:
            await self._bot.send_message(
                chat_id=self._chat_id,
                text=text,
                parse_mode="HTML",
            )
        except Forbidden as exc:
            log.error("Telegram Forbidden: %s", exc)
        except InvalidToken as exc:
            log.error("Telegram InvalidToken: %s", exc)

limiter = Limiter(key_func=get_remote_address)

_API_RATE_LIMIT = os.environ.get("TRADINGAGENTS_API_RATE_LIMIT", "10/minute")
_BG_RATE_LIMIT = os.environ.get("TRADINGAGENTS_BG_RATE_LIMIT", "5/minute")

# Set of currently-open WebSocket objects. Tracked so the lifespan teardown
# can force-close them; otherwise a handler stuck in `ws.receive()` will keep
# the ASGI portal from closing cleanly.
_active_ws: set[WebSocket] = set()


# --------- request/response models ---------


class WatchlistIn(BaseModel):
    ticker: str
    company_name: str = ""
    exchange: str = ""
    source: str = "user"


class WatchlistReorderIn(BaseModel):
    tickers: list[str]


class WatchlistUpdateIn(BaseModel):
    group: str | None = None


class RunIn(BaseModel):
    ticker: str
    force: bool = False


class DownloadTickersIn(BaseModel):
    tickers: list[str]
    format: str = "zip"


class IndicatorIn(BaseModel):
    kind: str = "vix"
    name: str | None = None
    threshold: float | None = None
    description: str | None = None
    enabled: bool = True


# --------- Background indicator scheduler ---------

_indicator_scheduler_running = False
_indicator_scheduler_stop = threading.Event()
_indicator_scheduler_thread: threading.Thread | None = None


def _maybe_send_change_notification(checks: list[dict]) -> None:
    """Compare checks to previous state and send Telegram if the triggered set changed."""
    try:
        cfg = storage.read_notifier_config()
        if not (cfg.get("enabled") and cfg.get("bot_token") and cfg.get("chat_id")):
            return
        previous = storage.read_indicator_state()
        diff = storage.diff_indicator_states(previous, checks)
        if not diff["changed"]:
            return
        from web.server.notifier import build_change_message

        notifier = _get_notifier()
        if not notifier:
            return
        message = build_change_message(diff)
        loop = events._get_event_loop()
        if loop is None:
            return
        asyncio.run_coroutine_threadsafe(notifier.send_raw(message), loop)
        storage.write_indicator_state(storage.build_state_from_checks(checks))
    except Exception:
        log.exception("Failed to send change notification")


def _run_indicator_check() -> None:
    """Run indicator check and send Telegram notification on status change."""
    try:
        checks = indicators.run_checks()
        _maybe_send_change_notification(checks)
    except Exception:
        log.exception("Background indicator check failed")


def _update_last_check_at() -> None:
    current_schedule = storage.read_indicator_schedule()
    if current_schedule.get("interval_ms", 0) > 0:
        current_schedule["last_check_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        storage.write_indicator_schedule(current_schedule)


def _indicator_background_loop() -> None:
    """Background thread: run indicator checks on the configured schedule."""
    while not _indicator_scheduler_stop.is_set():
        interval_ms = storage.read_indicator_schedule().get("interval_ms", 0)
        if interval_ms <= 0:
            # No schedule configured, sleep for 60s and recheck
            _indicator_scheduler_stop.wait(60)
            continue

        _indicator_scheduler_stop.wait(interval_ms / 1000)
        if _indicator_scheduler_stop.is_set():
            return

        try:
            _run_indicator_check()
        except Exception:
            log.exception("Indicator background check error")
        else:
            _update_last_check_at()


def _start_indicator_scheduler() -> None:
    global _indicator_scheduler_running, _indicator_scheduler_thread
    if _indicator_scheduler_running:
        return
    _indicator_scheduler_running = True
    _indicator_scheduler_stop.clear()
    _indicator_scheduler_thread = threading.Thread(target=_indicator_background_loop, daemon=True)
    _indicator_scheduler_thread.start()
    log.info("Indicator background scheduler started")


def _stop_indicator_scheduler() -> None:
    global _indicator_scheduler_running
    _indicator_scheduler_running = False
    _indicator_scheduler_stop.set()
    log.info("Indicator background scheduler stopping")


def _restart_indicator_scheduler() -> None:
    """Restart the scheduler (called when schedule config changes)."""
    _stop_indicator_scheduler()
    time.sleep(0.5)
    _start_indicator_scheduler()


# --------- lifespan ---------


def _price_broadcast(event: dict) -> None:
    """Sync adapter: ``PriceFeed.start`` expects a sync broadcast callable,
    but ``events._broadcast`` is async (it awaits ``ws.send_json``). We
    schedule the async broadcast on the feed's running loop so price
    ticks still fan out to WS global subscribers in production.
    No-op when called outside a running event loop (e.g. from tests
    that drive the poll loop synchronously with broadcast=None)."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    try:
        loop.create_task(events._broadcast(event))
    except RuntimeError as exc:
        log.warning("_price_broadcast: failed to schedule broadcast: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = settings_mod.get_settings()
    # Hardcoded legacy path: pre-Task-3 default was ~/.tradingagents/dashboard.db.
    # Remove if present so file-based storage starts truly fresh.
    legacy_db = Path.home() / ".tradingagents" / "dashboard.db"
    if legacy_db.exists():
        log.warning("removing legacy SQLite DB at %s (file-based storage only)", legacy_db)
        try:
            legacy_db.unlink()
        except OSError as exc:
            log.error("failed to remove legacy DB: %s", exc)
    storage.init_settings(data_dir=s.data_dir, cache_dir=s.cache_dir)
    from web.server.cloud_persistence import restore_watchlist

    restore_watchlist(s.data_dir)
    # Capture the main event loop so events.emit() (called from worker
    # threads inside loop.run_in_executor) can schedule broadcasts on it
    # via asyncio.run_coroutine_threadsafe. Without this, live WS
    # updates from inside a run silently never fire — the UI only
    # updated on reconnect (replay from events.jsonl).
    events.set_event_loop(asyncio.get_running_loop())
    lp_module.setup_log_publisher(
        asyncio.get_running_loop(), min_level=getattr(logging, s.log_level, logging.INFO)
    )
    orchestrator.set_event_loop(asyncio.get_running_loop())
    # Silence yfinance's own ERROR-level noise for delisted/foreign symbols
    # (e.g. "TA125: possibly delisted"). Without this, the dashboard log
    # fills with yfinance-internal tracebacks every poll for every bad
    # ticker in the watchlist.
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    # Mark any previously-running runs as failed (process restart recovery).
    for td in storage.walk_data_dir():
        try:
            subdirs = [sd for sd in td.iterdir() if sd.is_dir()]
        except PermissionError:
            continue
        for sd in subdirs:
            rj = storage.read_json(sd / "run.json")
            if rj and rj.get("status") == "running":
                storage.mark_run_status(
                    rj["id"],
                    status="failed",
                    finished_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                )
                log.warning("reaped stale running run %s", rj["id"])

    # Price-feed state. We always materialise ``PriceState`` on
    # ``app.state`` so ``GET /api/prices`` has something to read (the
    # frontend polls it on first paint, before any ticker exists — an
    # empty ``{}`` is the correct response, not a 404).
    #
    # The background ``PriceFeed`` itself is opt-in via env var so the
    # test suite can disable the network-touching yfinance poll loop.
    from . import price_feed as _pf

    app.state.price_state = _pf.PriceState(
        snapshots={},
        tickers=lambda: [r["ticker"] for r in queries.read_watchlist()],
    )
    if os.environ.get("TRADINGAGENTS_DASHBOARD_DISABLE_PRICE_FEED") != "1":
        feed = _pf.PriceFeed(app.state.price_state, poll_s=s.price_poll_s)
        feed.start(broadcast=_price_broadcast)
        app.state.price_feed = feed

    # Start the runner worker.
    await runner.start()

    # Auto-resume any background past-runs that were running when the
    # server last exited. Runs in the orchestrator's own threads;
    # the server startup is not blocked.
    from web.server import background_runs

    background_runs._load_existing_jobs()

    # Start the ticker accuracy agent background loop.
    from web.server.ticker_agent import orchestrator as _agent

    # Start the indicator background scheduler.
    _start_indicator_scheduler()

    yield
    # Stop the indicator scheduler before other shutdowns.
    _stop_indicator_scheduler()
    # Stop the price feed (if it was started) before the runner so any
    # in-flight poll iteration can complete without racing shutdown.
    feed = getattr(app.state, "price_feed", None)
    if feed is not None:
        await feed.stop()
    await runner.stop()
    lp_module.teardown_log_publisher()
    _agent.stop_background_loop()


def create_app() -> FastAPI:
    # Load .env into os.environ at startup so user-saved config (model,
    # provider, api key) is picked up by the trading graph on every run
    # without restarting the server process.
    _env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if _env_path.exists():
        for _line in _env_path.read_text(encoding="utf-8").splitlines():
            _s = _line.strip()
            if _s and not _s.startswith("#") and "=" in _s:
                _k, _, _v = _s.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

    from fastapi.responses import JSONResponse

    app = FastAPI(title="TradingAgents Dashboard", lifespan=lifespan)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        path = request.url.path
        if path.startswith("/api/") and not path.startswith("/api/auth/"):
            session = read_session(request)
            if not session:
                return JSONResponse(status_code=401, content={"detail": "Not authenticated"})
            request.state.user = session
        return await call_next(request)

    app.include_router(auth_router)
    app.include_router(chat_router)

    @app.get("/api/config/models")
    def config_models():
        env = _read_dotenv()
        return {
            "llm_provider": os.environ.get("TRADINGAGENTS_LLM_PROVIDER")
            or env.get("TRADINGAGENTS_LLM_PROVIDER")
            or DEFAULT_CONFIG.get("llm_provider"),
            "deep_think_model": os.environ.get("TRADINGAGENTS_DEEP_THINK_LLM")
            or env.get("TRADINGAGENTS_DEEP_THINK_LLM")
            or DEFAULT_CONFIG.get("deep_think_llm"),
            "quick_think_model": os.environ.get("TRADINGAGENTS_QUICK_THINK_LLM")
            or env.get("TRADINGAGENTS_QUICK_THINK_LLM")
            or DEFAULT_CONFIG.get("quick_think_llm"),
        }

    @app.get("/api/health")
    def health():
        return {
            "status": "ok",
            "uptime_s": 0,
            "watchlist_size": len(queries.read_watchlist()),
            "runs_in_queue": 0,
            "runs_running": 0,
        }

    @app.get("/api/watchlist")
    def list_watchlist() -> list[dict]:
        return [queries.watchlist_to_dict(r) for r in queries.read_watchlist()]

    @app.get("/api/prices")
    def list_prices() -> dict:
        return app.state.price_state.snapshots

    @app.get("/api/indicators")
    def list_indicators() -> dict:
        return {
            "indicators": [
                indicators._definition_to_dict(row) for row in indicators.read_indicators()
            ]
        }

    @app.post("/api/indicators")
    def post_indicator(body: IndicatorIn) -> dict:
        try:
            row = indicators.add_indicator(body.model_dump(exclude_none=True))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return indicators._definition_to_dict(row)

    @app.delete("/api/indicators/{indicator_id}", status_code=204)
    def delete_indicator(indicator_id: str) -> Response:
        if not indicators.remove_indicator(indicator_id):
            raise HTTPException(status_code=404, detail="indicator not found")
        return Response(status_code=204)

    @app.patch("/api/indicators/{indicator_id}")
    def patch_indicator(indicator_id: str, body: dict) -> dict:
        try:
            updated = indicators.update_indicator(indicator_id, body)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if updated is None:
            raise HTTPException(status_code=404, detail="indicator not found")
        return indicators._definition_to_dict(updated)

    @app.post("/api/indicators/reset")
    def reset_indicators() -> dict:
        return {
            "indicators": [
                indicators._definition_to_dict(row) for row in indicators.reset_indicators()
            ]
        }

    @app.post("/api/indicators/check")
    @limiter.limit(_BG_RATE_LIMIT)
    def check_indicators(request: Request) -> dict:
        checks = indicators.run_checks()
        _maybe_send_change_notification(checks)
        return {"checks": checks}

    @app.get("/api/indicators/schedule")
    def get_indicator_schedule() -> dict:
        return storage.read_indicator_schedule()

    @app.put("/api/indicators/schedule")
    def update_indicator_schedule(body: dict) -> dict:
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="Request body must be a JSON object")
        try:
            interval_ms = int(body.get("interval_ms", 0))
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="interval_ms must be a number") from None
        current = storage.read_indicator_schedule()
        payload = {"interval_ms": interval_ms}
        if current.get("last_check_at"):
            payload["last_check_at"] = current["last_check_at"]
        storage.write_indicator_schedule(payload)
        _restart_indicator_scheduler()
        return payload

    @app.post("/api/watchlist", status_code=201)
    def add_to_watchlist(body: WatchlistIn) -> dict:
        from . import price_feed as _pf

        try:
            _pf.validate_ticker_exists(body.ticker)
        except _pf.TickerNotFound as exc:
            detail = {"error": "ticker_not_found", "ticker": body.ticker, "reason": exc.reason}
            raise HTTPException(status_code=400, detail=detail) from exc
        try:
            row = queries.add_ticker(
                body.ticker, body.company_name, body.exchange, source=body.source
            )
        except queries.DuplicateTicker:
            raise HTTPException(status_code=409, detail="ticker already on watchlist") from None
        return queries.watchlist_to_dict(row)

    @app.delete("/api/watchlist/{ticker}", status_code=204)
    def remove_from_watchlist(ticker: str) -> Response:
        queries.remove_ticker(ticker)
        return Response(status_code=204)

    @app.patch("/api/watchlist/reorder")
    def reorder_watchlist(body: WatchlistReorderIn) -> list[dict]:
        queries.reorder_watchlist(body.tickers)
        return [queries.watchlist_to_dict(r) for r in queries.read_watchlist()]

    @app.patch("/api/watchlist/{ticker}")
    def update_watchlist_item(ticker: str, body: WatchlistUpdateIn) -> dict:
        row = queries.update_watchlist_item(ticker, group=body.group)
        if row is None:
            raise HTTPException(status_code=404, detail="ticker not found")
        return queries.watchlist_to_dict(row)

    @app.post("/api/runs", status_code=202)
    @limiter.limit(_API_RATE_LIMIT)
    async def start_run(request: Request, body: RunIn) -> dict:
        try:
            ticker = body.ticker.upper()
            if ticker not in {r["ticker"] for r in queries.read_watchlist()}:
                raise HTTPException(status_code=404, detail="ticker not on watchlist")
            date_str = storage.today_utc_iso()
            run_id = await runner.enqueue(
                ticker,
                date_str,
                force=bool(body.force),
                price_state=app.state.price_state,
            )
            return {"run_id": run_id}
        except HTTPException:
            raise
        except Exception:
            log.exception("start_run failed for ticker=%s", body.ticker)
            raise HTTPException(status_code=500, detail="start_run failed") from None

    @app.get("/api/tickers/{ticker}/runs")
    def list_ticker_runs(ticker: str, limit: int = 50) -> list[dict]:
        rows = storage.list_ticker_runs(ticker.upper(), limit=limit)
        return [queries.run_to_dict(r) for r in rows]

    @app.get("/api/tickers/{ticker}/history")
    def get_ticker_history(ticker: str, range: str = "auto") -> dict:
        from . import history as _history

        status, body = _history.get_history(ticker, range)
        if status != 200:
            raise HTTPException(status_code=status, detail=body)
        return body

    @app.get("/api/tickers/{ticker}/download")
    def download_ticker(ticker: str, format: str = "zip"):
        from . import download as _download

        safe = storage.safe_ticker_component(ticker).upper()

        if format == "json":
            data = _download.generate_ticker_json(ticker)
            buf = io.BytesIO(json.dumps(data, indent=2).encode("utf-8"))
            return StreamingResponse(
                buf,
                media_type="application/json",
                headers={"Content-Disposition": f"attachment; filename={safe}-data.json"},
            )
        elif format == "csv":
            csv_data = _download.generate_full_csv(ticker)
            buf = io.BytesIO(csv_data.encode("utf-8"))
            return StreamingResponse(
                buf,
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename={safe}-data.csv"},
            )
        else:
            buf = _download.generate_ticker_zip(ticker)
            return StreamingResponse(
                buf,
                media_type="application/zip",
                headers={"Content-Disposition": f"attachment; filename={safe}-data.zip"},
            )

    @app.post("/api/tickers/download")
    def download_tickers(body: DownloadTickersIn):
        from . import download as _download

        if not body.tickers:
            raise HTTPException(status_code=400, detail="tickers list cannot be empty")

        fmt = body.format or "zip"
        if fmt not in ("zip", "csv", "json"):
            raise HTTPException(status_code=400, detail="format must be zip, csv, or json")

        buf = io.BytesIO()

        if fmt == "json":
            for ticker in body.tickers:
                data = _download.generate_ticker_json(ticker)
                safe = storage.safe_ticker_component(ticker).upper()
                filename = f"{safe}-data.json"
                buf.write(json.dumps({filename: data}, indent=2).encode("utf-8"))
                buf.write(b"\n")
            buf.seek(0)
            return StreamingResponse(
                buf,
                media_type="application/json",
                headers={"Content-Disposition": "attachment; filename=tickers-bundle.json"},
            )
        elif fmt == "csv":
            for ticker in body.tickers:
                csv_data = _download.generate_full_csv(ticker)
                safe = storage.safe_ticker_component(ticker).upper()
                filename = f"{safe}-data.csv"
                buf.write(f"=== {filename} ===\n".encode())
                buf.write(csv_data.encode("utf-8"))
                buf.write(b"\n")
            buf.seek(0)
            return StreamingResponse(
                buf,
                media_type="text/csv",
                headers={"Content-Disposition": "attachment; filename=tickers-bundle.csv"},
            )
        else:
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for ticker in body.tickers:
                    ticker_buf = _download.generate_ticker_zip(ticker)
                    safe = storage.safe_ticker_component(ticker).upper()
                    filename = f"{safe}-data.zip"
                    zf.writestr(filename, ticker_buf.getvalue())
            buf.seek(0)
            return StreamingResponse(
                buf,
                media_type="application/zip",
                headers={"Content-Disposition": "attachment; filename=tickers-bundle.zip"},
            )

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict:
        rj = storage.read_run(run_id)
        if rj is None:
            raise HTTPException(status_code=404, detail="run not found")
        out = queries.run_to_dict(rj)
        out["events"] = [queries.event_to_dict(e, run_id) for e in storage.list_run_events(run_id)]
        out["llm_calls"] = [queries.llm_call_to_dict(c) for c in storage.list_run_llm_calls(run_id)]
        out["stages"] = _load_stages(run_id)
        return out

    @app.get("/api/runs/{run_id}/trace")
    def get_run_trace(run_id: str, since: str = "", limit: int = 500, kind: str = "") -> dict:
        rj = storage.read_run(run_id)
        if rj is None:
            raise HTTPException(status_code=404, detail="run not found")
        kinds: set[str] | None = None
        if kind:
            kinds = {k.strip() for k in kind.split(",") if k.strip()}
            valid = {"event", "stage", "llm_call"}
            bad = kinds - valid
            if bad:
                raise HTTPException(
                    status_code=400,
                    detail=f"unknown kind(s): {sorted(bad)}; valid: {sorted(valid)}",
                )
        limit = max(1, min(int(limit), 5000))
        return queries.build_trace(run_id, since=since, limit=limit, kinds=kinds)

    @app.get("/api/runs/{run_id}/health")
    def get_run_health(run_id: str) -> dict:
        result = queries.build_health(run_id)
        if not result.get("found"):
            raise HTTPException(status_code=404, detail="run not found")
        result["subscribers"] = len(events._subscribers.get(run_id, set()))
        return result

    @app.post("/api/runs/{run_id}/cancel")
    def cancel_run(run_id: str) -> dict:
        rj = storage.read_run(run_id)
        if rj is None:
            raise HTTPException(status_code=404, detail="run not found")
        storage.mark_run_status(run_id, cancel_requested=True)
        from web.server.runner import mark_run_cancelled
        mark_run_cancelled(run_id)
        return queries.run_to_dict(storage.read_run(run_id))

    @app.post("/api/runs/{run_id}/resume", status_code=202)
    async def resume_run(run_id: str) -> dict:
        try:
            new_run_id = await runner.resume_run(run_id, price_state=app.state.price_state)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"run_not_found: {run_id}") from None
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
        return {"run_id": new_run_id, "previous_run_id": run_id}

    @app.delete("/api/runs/{run_id}")
    def delete_run(run_id: str) -> dict:
        rj = storage.read_run(run_id)
        if rj is None:
            raise HTTPException(status_code=404, detail="run not found")
        ticker = rj.get("ticker", "")
        deleted = storage.delete_run(run_id)
        if ticker:
            queries.clear_last_run_if_matches(ticker, run_id)
        return {"deleted": deleted, "run_id": run_id, "ticker": ticker}

    class DeleteRunsIn(BaseModel):
        run_ids: list[str]

    @app.post("/api/runs/delete-bulk")
    def delete_runs_bulk(body: DeleteRunsIn) -> dict:
        results: list[dict] = []
        for run_id in body.run_ids:
            rj = storage.read_run(run_id)
            if rj is None:
                results.append({"run_id": run_id, "deleted": False, "error": "not_found"})
                continue
            ticker = rj.get("ticker", "")
            deleted = storage.delete_run(run_id)
            if ticker:
                queries.clear_last_run_if_matches(ticker, run_id)
            results.append({"run_id": run_id, "deleted": deleted, "ticker": ticker})
        return {
            "results": results,
            "total": len(results),
            "deleted": sum(1 for r in results if r["deleted"]),
        }

    @app.websocket("/ws/runs/{run_id}")
    async def ws_run(ws: WebSocket, run_id: str, since: str | None = None) -> None:
        session = read_session_from_ws(ws)
        if not session:
            await ws.close(code=4001)
            return
        await ws.accept()
        _active_ws.add(ws)
        rj = storage.read_run(run_id)
        if rj is None:
            await ws.send_json({"type": "error", "detail": "run not found"})
            await ws.close()
            return
        for ev in storage.list_run_events(run_id):
            if since and (ev.get("id") or "") <= since:
                continue
            await ws.send_json(ev)
        events.subscribe(run_id, ws)
        try:
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            events.unsubscribe(run_id, ws)
            _active_ws.discard(ws)

    @app.websocket("/ws/global")
    async def ws_global(ws: WebSocket) -> None:
        session = read_session_from_ws(ws)
        if not session:
            await ws.close(code=4001)
            return
        await ws.accept()
        _active_ws.add(ws)
        events.subscribe_global(ws)
        try:
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            events.unsubscribe_global(ws)
            _active_ws.discard(ws)

    @app.websocket("/ws/logs")
    async def ws_logs(ws: WebSocket) -> None:
        session = read_session_from_ws(ws)
        if not session:
            await ws.close(code=4001)
            return
        await ws.accept()
        lp = lp_module.log_publisher()
        if lp:
            lp.subscribe(ws)
        try:
            await ws.send_json(
                {
                    "type": "connected",
                    "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "id": str(uuid.uuid4()),
                }
            )
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            if lp:
                lp.unsubscribe(ws)

    # --- Background Past Runs ---
    from web.server import background_runs

    @app.post("/api/background-runs", status_code=201)
    @limiter.limit(_BG_RATE_LIMIT)
    def post_background_run(request: Request, body: dict):
        try:
            job_id = background_runs.start(
                ticker=body["ticker"],
                date_from=body["date_from"],
                date_to=body["date_to"],
                every=body.get("every", "1d"),
                parallel=body.get("parallel", 1),
            )
        except (KeyError, ValueError) as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
        return {"job_id": job_id}

    @app.get("/api/background-runs")
    def get_background_runs():
        return {"jobs": background_runs.list_jobs(limit=50)}

    @app.get("/api/background-runs/{job_id}")
    def get_background_run(job_id: str):
        try:
            return background_runs.get(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"job_not_found: {job_id}") from None

    @app.delete("/api/background-runs/{job_id}")
    def delete_background_run(job_id: str):
        try:
            background_runs.delete_job(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"job_not_found: {job_id}") from None
        return {"status": "ok"}

    @app.post("/api/background-runs/{job_id}/cancel")
    def post_background_run_cancel(job_id: str):
        try:
            background_runs.cancel(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"job_not_found: {job_id}") from None
        return {"status": "ok"}

    @app.post("/api/background-runs/{job_id}/pause")
    def post_background_run_pause(job_id: str):
        try:
            background_runs.pause(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"job_not_found: {job_id}") from None
        return {"status": "ok"}

    @app.post("/api/background-runs/{job_id}/resume")
    def post_background_run_resume(job_id: str):
        try:
            background_runs.resume(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"job_not_found: {job_id}") from None
        return {"status": "ok"}

    # --- Ticker Accuracy Agent ---
    app.include_router(ticker_agent_router)

    # --- Config (read/write .env) ---
    _ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"

    _CONFIG_KEYS = [
        "TRADINGAGENTS_LLM_PROVIDER",
        "TRADINGAGENTS_DEEP_THINK_LLM",
        "TRADINGAGENTS_QUICK_THINK_LLM",
        "TRADINGAGENTS_LLM_BACKEND_URL",
        "TRADINGAGENTS_OUTPUT_LANGUAGE",
        "TRADINGAGENTS_MAX_DEBATE_ROUNDS",
        "TRADINGAGENTS_MAX_RISK_ROUNDS",
        "TRADINGAGENTS_TEMPERATURE",
        "TRADINGAGENTS_BENCHMARK_TICKER",
        "TRADINGAGENTS_CHECKPOINT_ENABLED",
        "TRADINGAGENTS_LLM_CACHE_ENABLED",
        "AUTH_DISABLED",
    ]
    # Factory defaults sourced from tradingagents/default_config.py.
    # Built dynamically so changes to default_config.py are picked up
    # without updating this file.
    _CONFIG_DEFAULTS: dict[str, str] = {}
    for _env_var, _cfg_key in _ENV_OVERRIDES.items():
        if _env_var in _CONFIG_KEYS:
            _val = DEFAULT_CONFIG.get(_cfg_key)
            _CONFIG_DEFAULTS[_env_var] = "" if _val is None else str(_val)
    _API_KEY_ENVS = [
        "OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        "ANTHROPIC_API_KEY",
        "XAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "DASHSCOPE_API_KEY",
        "DASHSCOPE_CN_API_KEY",
        "ZHIPU_API_KEY",
        "ZHIPU_CN_API_KEY",
        "MINIMAX_API_KEY",
        "MINIMAX_CN_API_KEY",
        "OPENROUTER_API_KEY",
        "OPENAI_COMPATIBLE_API_KEY",
        "ALPHA_VANTAGE_API_KEY",
    ]

    def _read_dotenv() -> dict[str, str]:
        env_path = _ENV_PATH
        if not env_path.exists():
            return {}
        result: dict[str, str] = {}
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "=" in stripped:
                key, _, val = stripped.partition("=")
                result[key.strip()] = val.strip()
        return result

    def _write_dotenv(updates: dict[str, str]) -> dict[str, str]:
        env_path = _ENV_PATH
        lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
        seen: set[str] = set()
        out: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key, _, _ = stripped.partition("=")
                key = key.strip()
                seen.add(key)
                if key in updates:
                    out.append(f"{key}={updates[key]}")
                else:
                    out.append(line)
            else:
                out.append(line)
        for key, val in updates.items():
            if key not in seen:
                out.append(f"{key}={val}")
        env_path.write_text("\n".join(out) + "\n", encoding="utf-8")
        for key, val in updates.items():
            os.environ[key] = val
        return _read_dotenv()

    @app.get("/api/config")
    def get_config():
        env = _read_dotenv()
        cfg = {}
        for key in _CONFIG_KEYS:
            cfg[key] = os.environ.get(key) or env.get(key, "")
        return {"config": cfg, "api_keys": {}}

    @app.put("/api/config")
    def put_config(body: dict):
        updates = {}
        for key in _CONFIG_KEYS:
            if key in body:
                updates[key] = str(body[key])
        if "OPENAI_COMPATIBLE_API_KEY" in body:
            updates["OPENAI_COMPATIBLE_API_KEY"] = str(body["OPENAI_COMPATIBLE_API_KEY"])
        if not updates:
            raise HTTPException(status_code=400, detail="no recognised config keys")
        _write_dotenv(updates)
        cfg = {}
        env = _read_dotenv()
        for key in _CONFIG_KEYS:
            cfg[key] = os.environ.get(key) or env.get(key, "")
        return {"config": cfg, "status": "saved"}

    @app.get("/api/config/defaults")
    def get_config_defaults():
        return {"defaults": _CONFIG_DEFAULTS}

    @app.get("/api/version")
    def get_version():
        version_file = Path(__file__).resolve().parents[2] / "VERSION"
        version = version_file.read_text().strip() if version_file.exists() else "unknown"
        return {"version": version}

    # --- Notifier (Telegram) settings ---

    @app.get("/api/notifier/config", response_model=NotifierOut)
    def get_notifier_config() -> NotifierOut:
        cfg = storage.read_notifier_config()
        return NotifierOut(
            enabled=cfg.get("enabled", False),
            bot_token=cfg.get("bot_token"),
            chat_id=cfg.get("chat_id"),
        )

    @app.put("/api/notifier/config", response_model=NotifierOut)
    def update_notifier_config(body: NotifierIn) -> NotifierOut:
        cfg = storage.read_notifier_config()
        if body.enabled is not None:
            cfg["enabled"] = bool(body.enabled)
        if body.bot_token is not None:
            cfg["bot_token"] = body.bot_token.strip() or None
        if body.chat_id is not None:
            cfg["chat_id"] = body.chat_id.strip() or None
        storage.write_notifier_config(cfg)
        return NotifierOut(
            enabled=cfg.get("enabled", False),
            bot_token=cfg.get("bot_token"),
            chat_id=cfg.get("chat_id"),
        )

    @app.post("/api/notifier/test", status_code=202)
    @limiter.limit(_BG_RATE_LIMIT)
    async def test_notifier(request: Request) -> dict:
        cfg = storage.read_notifier_config()
        token = cfg.get("bot_token")
        chat_id = cfg.get("chat_id")
        if not token or not chat_id:
            raise HTTPException(status_code=400, detail="Telegram bot_token and chat_id must be configured")
        from telegram import Bot
        from telegram.error import Forbidden, InvalidToken

        bot = Bot(token=token)
        try:
            await bot.send_message(
                chat_id=chat_id,
                text="✅ <b>TradingAgents Notifier Test</b>\n<i>Your Telegram notifications are working!</i>",
                parse_mode="HTML",
            )
        except Forbidden as exc:
            raise HTTPException(status_code=400, detail=f"Chat ID {chat_id} is not authorized: {exc}") from exc
        except InvalidToken as exc:
            raise HTTPException(status_code=400, detail=f"Invalid bot token: {exc}") from exc
        return {"status": "sent", "chat_id": chat_id}

    # static mount (only if build dir exists)
    settings = settings_mod.get_settings()
    if os.path.isdir(settings.frontend_dist):
        app.mount("/", StaticFiles(directory=settings.frontend_dist, html=True), name="frontend")

    return app


def _load_stages(run_id: str) -> list[dict]:
    rd = storage.read_run_dir(run_id)
    if rd is None:
        return []
    out = []
    for sp in sorted((rd / "stages").glob("*.json")):
        d = storage.read_json(sp) or {}
        out.append(d)
    return out
