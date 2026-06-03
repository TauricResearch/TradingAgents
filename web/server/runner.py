"""Async orchestrator that wraps TradingAgentsGraph and emits typed events."""
from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.checkpointer import (
    clear_checkpoint,
    thread_id as framework_thread_id,
)
from tradingagents.graph.trading_graph import TradingAgentsGraph

from web.server import db, events
from web.server.retry import compute_backoff, detect_rate_limit


log = logging.getLogger(__name__)

MAX_CONCURRENT = int(os.environ.get("TRADINGAGENTS_DASHBOARD_MAX_CONCURRENT", "3"))


def checkpoint_thread_id(ticker: str, date_str: str) -> str:
    """Mirror of ``tradingagents.graph.checkpointer.thread_id`` for tests."""
    return framework_thread_id(ticker, date_str)


def clear_today_checkpoint(ticker: str, date_str: str) -> None:
    """Used by force=True to drop the LangGraph thread state for today."""
    from . import storage
    clear_checkpoint(str(storage.cache_dir()), ticker, date_str)

# Retry policy. See docs/superpowers/specs/2026-06-02-rate-aware-retry-design.md
MAX_ATTEMPTS = 4
MAX_BACKOFF_S = 60.0


# Stage map: LangGraph node name -> (stage_key, report_field).
# The runner is the only place that knows how to interpret the
# per-node report; the graph just emits the raw delta.
_STAGE_MAP = {
    "Market Analyst": ("market", "market_report"),
    "Sentiment Analyst": ("sentiment", "sentiment_report"),
    "News Analyst": ("news", "news_report"),
    "Fundamentals Analyst": ("fundamentals", "fundamentals_report"),
    "Bull Researcher": ("research", None),
    "Bear Researcher": ("research", None),
    "Research Manager": ("research", "investment_plan"),
    "Trader": ("trader", "trader_investment_plan"),
    "Aggressive Analyst": ("risk", None),
    "Conservative Analyst": ("risk", None),
    "Neutral Analyst": ("risk", None),
}


def _stage_summary_for_node(node_name: str, delta: dict):
    """Return (stage_key, summary, excerpt, full_text) for analyst_completed,
    or (None, None, None, None) to skip."""
    if node_name not in _STAGE_MAP:
        return (None, None, None, None)
    stage, report_field = _STAGE_MAP[node_name]
    full_text = None
    excerpt = None
    if report_field:
        full_text = (delta or {}).get(report_field, "") or None
        excerpt = full_text
        if excerpt and len(excerpt) > 200:
            excerpt = excerpt[:200] + "\u2026"
    return (stage, "completed", excerpt, full_text)


def _format_traceback(exc: BaseException) -> str:
    """Render a compact, JSON-safe traceback string for inclusion in event payloads."""
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))


def build_graph(config=None, *, callbacks=None):
    """Build a TradingAgentsGraph. Tests monkeypatch this.

    The ``callbacks`` kwarg is forwarded to ``TradingAgentsGraph(callbacks=...)``
    so a StreamingCallbackHandler can be attached at the graph level. Tests
    can pass an empty list when they don't care.
    """
    return TradingAgentsGraph(
        config=config or DEFAULT_CONFIG,
        callbacks=callbacks or [],
    )


_WORK_QUEUE: asyncio.Queue = None  # type: ignore
_workers: list[asyncio.Task] = []
_sem: asyncio.Semaphore = None  # type: ignore
_active = 0
_idle = threading.Event()
_idle.set()


async def enqueue(ticker: str, date_str: str, force: bool = False) -> str:
    """Resolve today's run for ``ticker`` and either resume or start fresh.

    Returns the ``run_id`` (a string of the form ``TICKER:UTC_ISO``).

    Rules:
    - force=true: clear the LangGraph thread state for today, mark any
      existing partial as ``superseded``, create a new run dir + run.json.
    - force=false:
        - If today's run is already terminal (done/failed/cancelled/
          superseded), return that run_id without starting anything.
        - If today's run is ``running`` (partial), reuse its dir; the
          framework's thread_id will match the existing SqliteSaver
          checkpoint and resume from the last completed node.
        - If no run for today, create a fresh run dir + enqueue.
    """
    from . import storage
    ticker_u = ticker.upper()

    existing = storage.find_resumable_run(ticker_u, date_str)
    if existing and not force:
        run_json = existing["run_json"]
        status = run_json.get("status")
        if status == "running":
            log.info("resuming run %s for %s", existing["run_id"], ticker_u)
            return existing["run_id"]
        log.info("idempotent: returning existing %s run %s", status, existing["run_id"])
        return existing["run_id"]

    if existing and force:
        storage.mark_run_superseded(existing["run_id"])
        clear_today_checkpoint(ticker_u, date_str)
        log.info("force=true: superseded %s", existing["run_id"])

    info = storage.create_run_dir(ticker_u)
    run_id = info["run_id"]
    await _WORK_QUEUE.put((run_id, ticker_u, date_str, info["run_dir"]))
    return run_id


async def start(num_workers: int = 1) -> None:
    global _WORK_QUEUE, _sem
    _WORK_QUEUE = asyncio.Queue()
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
        if _WORK_QUEUE is None or (_WORK_QUEUE.empty() and _active == 0):
            return
        await asyncio.sleep(0.05)
    raise TimeoutError("runner did not become idle in time")


async def _worker_loop() -> None:
    global _active
    assert _WORK_QUEUE is not None and _sem is not None
    while True:
        run_id, ticker, date_str, run_dir = await _WORK_QUEUE.get()
        try:
            await _sem.acquire()
        except Exception:
            continue
        _active += 1
        asyncio.create_task(_run_one(run_id, ticker, date_str, run_dir, _sem))


async def _run_one(run_id: str, ticker: str, date_str: str, run_dir: Path, sem: asyncio.Semaphore) -> None:
    """Execute a single run. Full implementation in Task 11."""
    global _active
    try:
        _active += 1
        log.warning("_run_one stub called for %s — Task 11 will implement", run_id)
    finally:
        _active -= 1
        sem.release()


class _CancelSentinel(Exception):
    pass
