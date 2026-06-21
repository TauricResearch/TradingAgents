"""FastAPI application factory for the TradingAgents dashboard."""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import storage, queries, events, llm_calls, runner, settings as settings_mod
from tradingagents.default_config import DEFAULT_CONFIG, _ENV_OVERRIDES
from web.server.ticker_agent import orchestrator
from web.server.ticker_agent.router import router as ticker_agent_router


log = logging.getLogger(__name__)


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
    loop.create_task(events._broadcast(event))


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
    # Capture the main event loop so events.emit() (called from worker
    # threads inside loop.run_in_executor) can schedule broadcasts on it
    # via asyncio.run_coroutine_threadsafe. Without this, live WS
    # updates from inside a run silently never fire — the UI only
    # updated on reconnect (replay from events.jsonl).
    events.set_event_loop(asyncio.get_running_loop())
    orchestrator.set_event_loop(asyncio.get_running_loop())
    # Silence yfinance's own ERROR-level noise for delisted/foreign symbols
    # (e.g. "TA125: possibly delisted"). Without this, the dashboard log
    # fills with yfinance-internal tracebacks every poll for every bad
    # ticker in the watchlist.
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    # Mark any previously-running runs as failed (process restart recovery).
    for td in storage.walk_data_dir():
        for sd in td.iterdir():
            if not sd.is_dir():
                continue
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

    yield
    # Stop the price feed (if it was started) before the runner so any
    # in-flight poll iteration can complete without racing shutdown.
    feed = getattr(app.state, "price_feed", None)
    if feed is not None:
        await feed.stop()
    await runner.stop()
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

    app = FastAPI(title="TradingAgents Dashboard", lifespan=lifespan)

    @app.get("/api/config/models")
    def config_models():
        env = _read_dotenv()
        return {
            "llm_provider": os.environ.get("TRADINGAGENTS_LLM_PROVIDER") or env.get("TRADINGAGENTS_LLM_PROVIDER") or DEFAULT_CONFIG.get("llm_provider"),
            "deep_think_model": os.environ.get("TRADINGAGENTS_DEEP_THINK_LLM") or env.get("TRADINGAGENTS_DEEP_THINK_LLM") or DEFAULT_CONFIG.get("deep_think_llm"),
            "quick_think_model": os.environ.get("TRADINGAGENTS_QUICK_THINK_LLM") or env.get("TRADINGAGENTS_QUICK_THINK_LLM") or DEFAULT_CONFIG.get("quick_think_llm"),
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

    @app.post("/api/watchlist", status_code=201)
    def add_to_watchlist(body: WatchlistIn) -> dict:
        from . import price_feed as _pf
        try:
            _pf.validate_ticker_exists(body.ticker)
        except _pf.TickerNotFound as exc:
            detail = {"error": "ticker_not_found", "ticker": body.ticker, "reason": exc.reason}
            raise HTTPException(status_code=400, detail=detail)
        try:
            row = queries.add_ticker(body.ticker, body.company_name, body.exchange, source=body.source)
        except queries.DuplicateTicker:
            raise HTTPException(status_code=409, detail="ticker already on watchlist")
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
    async def start_run(body: RunIn) -> dict:
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
                raise HTTPException(status_code=400, detail=f"unknown kind(s): {sorted(bad)}; valid: {sorted(valid)}")
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
        return queries.run_to_dict(storage.read_run(run_id))

    @app.post("/api/runs/{run_id}/resume", status_code=202)
    async def resume_run(run_id: str) -> dict:
        try:
            new_run_id = await runner.resume_run(run_id, price_state=app.state.price_state)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"run_not_found: {run_id}")
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
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
        return {"results": results, "total": len(results), "deleted": sum(1 for r in results if r["deleted"])}

    @app.websocket("/ws/runs/{run_id}")
    async def ws_run(ws: WebSocket, run_id: str, since: Optional[str] = None) -> None:
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

    # --- Background Past Runs ---
    from web.server import background_runs

    @app.post("/api/background-runs", status_code=201)
    def post_background_run(body: dict):
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
        existing = _read_dotenv()
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
        api_keys = {}
        for key in _API_KEY_ENVS:
            raw = os.environ.get(key) or env.get(key, "")
            api_keys[key] = bool(raw)
        return {"config": cfg, "api_keys": api_keys}

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