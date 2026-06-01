"""FastAPI application factory for the TradingAgents dashboard."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from web.server import db, events, price_feed, runner
from web.server.settings import get_settings


log = logging.getLogger(__name__)


# Per-run subscriber lists. _subs[run_id] = set of asyncio.Queue.
_subs: dict[int, set[asyncio.Queue]] = {}

# Set of currently-open WebSocket objects. Tracked so the lifespan teardown
# can force-close them; otherwise a handler stuck in `ws.receive()` will keep
# the ASGI portal from closing cleanly.
_active_ws: set[WebSocket] = set()

# Stash the FastAPI event loop here at startup so `_broadcast` (called from
# worker threads) can schedule puts via `loop.call_soon_threadsafe`.
# `asyncio.Queue.put_nowait` is not thread-safe across event loops and does
# not wake the loop, so direct calls from other threads silently lose events.
_broadcast_loop: Optional[asyncio.AbstractEventLoop] = None


def _broadcast(run_id: int, evt: dict) -> None:
    loop = _broadcast_loop
    if loop is None:
        return
    for q in list(_subs.get(run_id, ())):
        try:
            loop.call_soon_threadsafe(q.put_nowait, evt)
        except Exception:
            pass


async def _close_all_ws() -> None:
    """Close every active WebSocket. Called from the lifespan finally block.

    This unblocks any client stuck in `receive_json()` (the receive will
    raise on the close frame) and lets the WS handler exit, so the ASGI
    portal can shut down cleanly. Each close is awaited so the close
    frame is actually flushed before the loop tears down.
    """
    for ws in list(_active_ws):
        try:
            await asyncio.wait_for(ws.close(code=1001, reason="server shutdown"), timeout=1.0)
        except Exception:
            pass


events.set_broadcast(_broadcast)


# --------- request/response models ---------

class WatchlistIn(BaseModel):
    ticker: str
    company_name: str = ""
    exchange: str = ""


class RunIn(BaseModel):
    ticker: str


# --------- lifespan ---------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _broadcast_loop
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    db.init_db()
    db.reap_stale_runs(timeout_s=600)

    state = price_feed.PriceState(
        snapshots={},
        tickers=lambda: [w.ticker for w in db.list_watchlist()],
    )
    feed = price_feed.PriceFeed(state, poll_s=settings.price_poll_s)

    # start runner
    await runner.start(num_workers=1)
    feed.start(broadcast=_broadcast)
    app.state.price_feed = feed
    app.state.price_state = state
    # Stash the running loop so `_broadcast` (called from worker threads)
    # can schedule puts via `call_soon_threadsafe`.
    _broadcast_loop = asyncio.get_running_loop()
    try:
        yield
    finally:
        _broadcast_loop = None
        # Force-close any open WebSockets so handlers exit and the portal
        # can shut down (clients blocked in receive_json() get a clean
        # disconnect and unblock their threads).
        await _close_all_ws()
        await feed.stop()
        await runner.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="TradingAgents Dashboard", lifespan=lifespan)

    @app.get("/api/health")
    def health():
        return {
            "status": "ok",
            "uptime_s": 0,  # simple; real uptime tracked by external process
            "watchlist_size": len(db.list_watchlist()),
            "runs_in_queue": 0,
            "runs_running": 0,
        }

    @app.get("/api/watchlist")
    def list_watch():
        return [_w_to_dict(w) for w in db.list_watchlist()]

    @app.post("/api/watchlist", status_code=201)
    def add_watch(row: WatchlistIn):
        from web.server.db import Watchlist, DuplicateTicker
        try:
            db.add_watchlist(Watchlist(
                ticker=row.ticker.upper(),
                company_name=row.company_name,
                exchange=row.exchange,
                added_at=datetime.utcnow(),
            ))
        except DuplicateTicker:
            raise HTTPException(status_code=409, detail={"error": "already_in_watchlist"})
        return _w_to_dict(db.list_watchlist()[[w.ticker for w in db.list_watchlist()].index(row.ticker.upper())])

    @app.delete("/api/watchlist/{ticker}", status_code=204)
    def del_watch(ticker: str):
        db.remove_watchlist(ticker.upper())
        return JSONResponse(status_code=204, content=None)

    @app.get("/api/prices")
    def prices():
        return app.state.price_state.snapshots

    @app.post("/api/runs", status_code=201)
    def create_run(row: RunIn):
        from datetime import date
        rid = runner.enqueue(row.ticker.upper(), idempotency_key=f"{row.ticker.upper()}:{date.today().isoformat()}")
        return {"run_id": rid}

    @app.get("/api/runs")
    def list_runs(limit: int = 20):
        return [_run_to_dict(r) for r in db.list_runs(limit=limit)]

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: int):
        run = db.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run_not_found")
        return {
            "run": _run_to_dict(run),
            "events": [_event_to_dict(e) for e in db.events_for_run(run_id)],
        }

    @app.post("/api/runs/{run_id}/cancel")
    def cancel_run(run_id: int):
        db.request_cancellation(run_id)
        return {"cancelled": True}

    @app.websocket("/ws/runs/{run_id}")
    async def ws_run(ws: WebSocket, run_id: int, since: int = 0):
        await ws.accept()
        _active_ws.add(ws)
        # Replay persisted events since `since`
        for e in db.events_for_run(run_id, since_id=since):
            await ws.send_json({
                "v": 1,
                "type": e.type,
                "ts": e.ts.isoformat() + "Z",
                "run_id": e.run_id,
                "data": json.loads(e.payload_json),
                "id": e.id,
            })
        # Subscribe to live
        q: asyncio.Queue = asyncio.Queue(maxsize=1024)
        _subs.setdefault(run_id, set()).add(q)

        # Background task: calls ws.receive() so we actually see the
        # ASGI `websocket.disconnect` message and flip client_state.
        # (Polling `ws.client_state` alone never detects a closed socket
        # because starlette only updates that state inside `receive()`.)
        disconnect = asyncio.Event()

        async def _watch_close():
            try:
                while True:
                    msg = await ws.receive()
                    if msg.get("type") == "websocket.disconnect":
                        break
            except WebSocketDisconnect:
                pass
            except Exception:
                pass
            finally:
                disconnect.set()

        watcher = asyncio.create_task(_watch_close())
        try:
            while True:
                try:
                    evt = await asyncio.wait_for(q.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    # No event in 0.5s. Check (a) client disconnect and
                    # (b) server shutdown.
                    if disconnect.is_set() or _broadcast_loop is None:
                        break
                    continue
                await ws.send_json(evt)
        except WebSocketDisconnect:
            pass
        finally:
            _subs.get(run_id, set()).discard(q)
            if not _subs.get(run_id):
                _subs.pop(run_id, None)
            _active_ws.discard(ws)
            watcher.cancel()
            try:
                await watcher
            except BaseException:
                pass

    # static mount (only if build dir exists)
    settings = get_settings()
    if os.path.isdir(settings.frontend_dist):
        app.mount("/", StaticFiles(directory=settings.frontend_dist, html=True), name="frontend")

    return app


def _w_to_dict(w) -> dict:
    return {
        "ticker": w.ticker,
        "company_name": w.company_name,
        "exchange": w.exchange,
        "added_at": w.added_at.isoformat() if w.added_at else None,
        "last_decision": w.last_decision,
        "last_decision_at": w.last_decision_at.isoformat() if w.last_decision_at else None,
    }


def _run_to_dict(r) -> dict:
    return {
        "id": r.id,
        "ticker": r.ticker,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        "status": r.status,
        "decision_action": r.decision_action,
        "decision_target": r.decision_target,
        "decision_rationale": r.decision_rationale,
        "decision_confidence": r.decision_confidence,
    }


def _event_to_dict(e) -> dict:
    import json
    return {
        "id": e.id,
        "type": e.type,
        "ts": e.ts.isoformat() if e.ts else None,
        "data": json.loads(e.payload_json),
    }
