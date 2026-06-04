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
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import storage, queries, events, llm_calls, runner, settings as settings_mod


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
    yield
    # Stop the price feed (if it was started) before the runner so any
    # in-flight poll iteration can complete without racing shutdown.
    feed = getattr(app.state, "price_feed", None)
    if feed is not None:
        await feed.stop()
    await runner.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="TradingAgents Dashboard", lifespan=lifespan)

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
        # In-memory snapshot maintained by the background PriceFeed
        # (started in the lifespan below). FastAPI's jsonable_encoder
        # serialises the PriceSnapshot dataclass fields directly.
        return app.state.price_state.snapshots

    @app.post("/api/watchlist", status_code=201)
    def add_to_watchlist(body: WatchlistIn) -> dict:
        # Validate the ticker against yfinance so delisted/foreign symbols
        # are rejected up front (HTTP 400) instead of silently going stale
        # in the price feed forever after.
        from . import price_feed as _pf
        try:
            _pf.validate_ticker_exists(body.ticker)
        except _pf.TickerNotFound as exc:
            detail = {"error": "ticker_not_found", "ticker": body.ticker, "reason": exc.reason}
            raise HTTPException(status_code=400, detail=detail)
        try:
            row = queries.add_ticker(body.ticker, body.company_name, body.exchange)
        except queries.DuplicateTicker:
            raise HTTPException(status_code=409, detail="ticker already on watchlist")
        return queries.watchlist_to_dict(row)

    @app.delete("/api/watchlist/{ticker}", status_code=204)
    def remove_from_watchlist(ticker: str) -> Response:
        queries.remove_ticker(ticker)
        return Response(status_code=204)

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
    def get_run_trace(
        run_id: str,
        since: str = "",
        limit: int = 500,
        kind: str = "",
    ) -> dict:
        """Merged chronological timeline of events + stages + LLM calls.

        Used by the dashboard's "trace" view to render a single ordered
        list (rather than three separate sections). Each item carries
        a ``kind`` discriminator (``event`` | ``stage`` | ``llm_call``)
        and a ``ts`` field; the rest of the shape is per-kind.

        Query params:
          - ``since``: skip items with ``ts <= since`` (use an item id
            from a prior response for a live tail).
          - ``limit``: cap the number of items (default 500, max 5000).
          - ``kind``: comma-separated subset of ``event,stage,llm_call``
            to include; default is all three.
        """
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
        """Liveness + progress summary for a run.

        Returns the run status, the most recent event (with age in
        seconds), the inferred current node, LLM call + token totals,
        and an ``is_alive`` boolean. A "running" run whose most recent
        event is older than ~5 minutes is reported as ``is_stale``
        (separate from ``is_alive``) so a UI can distinguish "stuck"
        from "in-flight but waiting on a slow LLM call".
        """
        result = queries.build_health(run_id)
        if not result.get("found"):
            raise HTTPException(status_code=404, detail="run not found")
        # ``subscribers`` is per-run only; the global stream is not counted
        # because it doesn't tie a viewer to this run.
        result["subscribers"] = len(events._subscribers.get(run_id, set()))
        return result

    @app.post("/api/runs/{run_id}/cancel")
    def cancel_run(run_id: str) -> dict:
        rj = storage.read_run(run_id)
        if rj is None:
            raise HTTPException(status_code=404, detail="run not found")
        storage.mark_run_status(run_id, cancel_requested=True)
        return queries.run_to_dict(storage.read_run(run_id))

    @app.websocket("/ws/runs/{run_id}")
    async def ws_run(ws: WebSocket, run_id: str, since: Optional[str] = None) -> None:
        await ws.accept()
        _active_ws.add(ws)
        rj = storage.read_run(run_id)
        if rj is None:
            await ws.send_json({"type": "error", "detail": "run not found"})
            await ws.close()
            return
        # Replay events for the run. If ``since`` was provided (the id of
        # the last event the client already received on a previous
        # connection), skip events with id <= since so the client only
        # gets the gap plus any new live events.
        for ev in storage.list_run_events(run_id):
            if since and (ev.get("id") or "") <= since:
                continue
            await ws.send_json(ev)
        events.subscribe(run_id, ws)
        try:
            while True:
                # Drain client messages; we don't act on them.
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            events.unsubscribe(run_id, ws)
            _active_ws.discard(ws)

    @app.websocket("/ws/global")
    async def ws_global(ws: WebSocket) -> None:
        """Stream all live events (any run) to the client.

        The frontend's ``useGlobalStream`` hook connects here for app-wide
        real-time updates (price ticks, etc.). It is *not* the per-run
        event log — that lives on ``/ws/runs/{run_id}`` and replays from
        disk on connect. The global stream is a live-only fanout.

        This endpoint exists because the frontend always opens the global
        stream on dashboard mount. Without a matching route, the WS
        request falls through to the ``StaticFiles`` mount at ``/`` and
        crashes the ASGI app with ``AssertionError: scope["type"] == "http"``.
        """
        await ws.accept()
        _active_ws.add(ws)
        events.subscribe_global(ws)
        try:
            while True:
                # Drain client messages; we don't act on them.
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            events.unsubscribe_global(ws)
            _active_ws.discard(ws)

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