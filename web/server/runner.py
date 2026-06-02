"""Async orchestrator that wraps TradingAgentsGraph and emits typed events."""
from __future__ import annotations

import asyncio
import logging
import os
import random
import threading
import time
from datetime import datetime, timezone
from typing import Optional

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

from web.server import db, events


log = logging.getLogger(__name__)

MAX_CONCURRENT = int(os.environ.get("TRADINGAGENTS_DASHBOARD_MAX_CONCURRENT", "3"))


def build_graph(config=None):
    """Build a TradingAgentsGraph. Tests monkeypatch this."""
    # NOTE: TradingAgentsGraph.__init__'s first positional arg is
    # ``selected_analysts`` (a list of strings). Passing the config dict
    # positionally makes it iterate dict.keys() looking for analyst names
    # and crash on the first non-analyst key (e.g. ``"project_dir"``).
    # Always pass the config as the keyword argument.
    return TradingAgentsGraph(config=config or DEFAULT_CONFIG)


_queue: asyncio.Queue = None  # type: ignore
_workers: list[asyncio.Task] = []
_sem: asyncio.Semaphore = None  # type: ignore
_active = 0
_idle = threading.Event()
_idle.set()


def enqueue(ticker: str, *, idempotency_key: str) -> int:
    if _queue is None:
        raise RuntimeError("runner.start() must be called before enqueue()")
    rid = db.create_run(ticker=ticker, idempotency_key=idempotency_key)
    _queue.put_nowait(rid)
    return rid


async def start(num_workers: int = 1) -> None:
    global _queue, _sem
    _queue = asyncio.Queue()
    _sem = asyncio.Semaphore(MAX_CONCURRENT)
    for _ in range(num_workers):
        _workers.append(asyncio.create_task(_worker_loop()))


async def stop() -> None:
    for w in _workers:
        w.cancel()
    for w in _workers:
        try:
            await w
        except BaseException:
            pass
    _workers.clear()


async def _wait_for_idle(timeout: float = 30) -> None:
    """Test helper: wait until the queue is empty and no run is in flight."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _queue is None or (_queue.empty() and _active == 0):
            return
        await asyncio.sleep(0.05)
    raise TimeoutError("runner did not become idle in time")


async def _worker_loop() -> None:
    global _active
    assert _queue is not None and _sem is not None
    while True:
        rid = await _queue.get()
        try:
            await _sem.acquire()
        except Exception:
            continue
        _active += 1
        asyncio.create_task(_run_one(rid, _sem))


async def _run_one(rid: int, sem: asyncio.Semaphore) -> None:
    global _active
    try:
        run = db.get_run(rid)
        if run is None:
            return
        if run.cancel_requested:
            db.mark_run_failed(rid, "cancelled")
            events.emit(rid, "run_failed", {"reason": "cancelled"})
            return

        events.emit(rid, "run_started", {"ticker": run.ticker})
        graph = build_graph()

        def cb(node_name: str, payload: dict) -> None:
            mapping = {
                "node_entered": "analyst_started",
            }
            type_ = mapping.get(node_name, node_name)
            if db.get_run(rid).cancel_requested:
                raise _CancelSentinel()
            events.emit(rid, type_, {"node": payload.get("node", node_name), **payload})

        loop = asyncio.get_event_loop()
        retries = 3
        last_err = None
        trade_date = datetime.now(timezone.utc).date().isoformat()

        def _do_propagate():
            return graph.propagate(run.ticker, trade_date, event_callback=cb)

        for attempt in range(retries + 1):
            try:
                final = await loop.run_in_executor(None, _do_propagate)
                break
            except _CancelSentinel:
                db.mark_run_failed(rid, "cancelled")
                events.emit(rid, "run_failed", {"reason": "cancelled"})
                return
            except asyncio.CancelledError:
                db.mark_run_failed(rid, "cancelled")
                events.emit(rid, "run_failed", {"reason": "cancelled"})
                return
            except Exception as e:
                last_err = e
                if "429" in str(e) and attempt < retries:
                    await asyncio.sleep(0.1 * (2 ** attempt) + random.random() * 0.1)
                    events.emit(rid, "tool_call_warning", {"message": f"retrying after {type(e).__name__}"})
                    continue
                db.mark_run_failed(rid, f"{type(e).__name__}: {e}")
                events.emit(rid, "run_failed", {"reason": "exception", "exception_class": type(e).__name__, "message": str(e)})
                return
        else:
            db.mark_run_failed(rid, f"exhausted retries: {last_err}")
            events.emit(rid, "run_failed", {"reason": "exhausted_retries"})
            return

        if db.get_run(rid).cancel_requested:
            db.mark_run_failed(rid, "cancelled")
            events.emit(rid, "run_failed", {"reason": "cancelled"})
            return

        decision = (final or {}).get("decision") or {}
        action = decision.get("action")
        target = decision.get("target")
        rationale = decision.get("rationale", "")
        confidence = decision.get("confidence", 0.0)
        db.mark_run_done(rid, decision_action=action or "HOLD", decision_target=target, decision_rationale=rationale, decision_confidence=confidence)
        db.update_watchlist_last_decision(run.ticker, rid, f"{action} @ {target}" if target else (action or ""), datetime.now(timezone.utc))
        events.emit(rid, "run_finished", {"duration_s": 0})
    finally:
        _active -= 1
        sem.release()


class _CancelSentinel(Exception):
    pass
