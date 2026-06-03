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

from web.server import events, storage
from web.server import queries as queries_module
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


_NODE_STATE_KEY = {
    "market_analyst": "market_report",
    "social_analyst": "sentiment_report",
    "news_analyst": "news_report",
    "fundamentals_analyst": "fundamentals_report",
    "bull_researcher": "investment_debate_state.bull_history",
    "bear_researcher": "investment_debate_state.bear_history",
    "research_manager": "investment_plan",
    "trader": "trader_investment_plan",
    "risky_analyst": "risk_debate_state.risky_history",
    "safe_analyst": "risk_debate_state.safe_history",
    "neutral_analyst": "risk_debate_state.neutral_history",
    "risk_manager": "final_trade_decision",
}


def _state_key_for_node(node_name: str) -> str:
    return _NODE_STATE_KEY.get(node_name, node_name)


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
    """Execute a single run with file-based storage."""
    global _active
    t_start = time.monotonic()
    try:
        run_json = storage.read_run(run_id)
        if run_json is None:
            return
        if run_json.get("cancel_requested"):
            storage.mark_run_status(run_id, status="failed", finished_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), error="cancelled")
            events.emit(run_id, "run_failed", {"reason": "cancelled"})
            return

        events.emit(run_id, "run_started", {"ticker": ticker})

        from web.server.callbacks import CaptureCallbackHandler, StreamingCallbackHandler
        stream_handler = StreamingCallbackHandler(run_id=run_id)
        capture_handler = CaptureCallbackHandler(run_id=run_id, ticker=ticker)

        loop = asyncio.get_event_loop()

        config = {
            **DEFAULT_CONFIG,
            "ticker": ticker,
            "trade_date": date_str,
            "checkpoint_enabled": True,
        }
        graph = build_graph(config, callbacks=[stream_handler, capture_handler])

        def cb(node_name: str, payload: dict) -> None:
            rj = storage.read_run(run_id)
            if rj and rj.get("cancel_requested"):
                raise _CancelSentinel()
            if node_name == "node_entered":
                capture_handler.current_node = payload.get("node", node_name)
                events.emit(run_id, "analyst_started", {"node": payload.get("node", node_name), **payload})
            elif node_name == "node_exited":
                stage, summary, excerpt, full_text = _stage_summary_for_node(
                    payload.get("node", ""), payload.get("delta", {})
                )
                if stage is None:
                    return
                data: dict = {"stage": stage, "summary": summary}
                if excerpt:
                    data["report_excerpt"] = excerpt
                if full_text:
                    data["report_text"] = full_text
                events.emit(run_id, "analyst_completed", data)
                # Persist the stage result to disk.
                node = payload.get("node", "")
                stage_name = _STAGE_MAP.get(node, (node,))[0]
                storage.write_stage(
                    run_id,
                    stage_name,
                    {
                        "stage": stage_name,
                        "node": node,
                        "state_key": _state_key_for_node(node),
                        "completed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                        "duration_ms": 0,
                        "value": summary,
                    },
                )
            else:
                events.emit(run_id, node_name, payload)

        def _do_propagate():
            return graph.propagate(ticker, date_str, event_callback=cb)

        final_state = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                final_state, final_signal = await loop.run_in_executor(None, _do_propagate)
                break
            except _CancelSentinel:
                storage.mark_run_status(run_id, status="failed", finished_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), error="cancelled")
                events.emit(run_id, "run_failed", {"reason": "cancelled"})
                return
            except asyncio.CancelledError:
                storage.mark_run_status(run_id, status="failed", finished_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), error="cancelled")
                events.emit(run_id, "run_failed", {"reason": "cancelled"})
                return
            except Exception as e:
                if detect_rate_limit(e) and attempt < MAX_ATTEMPTS - 1:
                    wait_s = compute_backoff(attempt, e, max_s=MAX_BACKOFF_S)
                    events.emit(run_id, "tool_call_warning", {
                        "message": f"rate limited; sleeping {wait_s:.1f}s before retry {attempt+1}/{MAX_ATTEMPTS-1}",
                        "retry_after_s": wait_s,
                        "exception_class": type(e).__name__,
                    })
                    log.warning(
                        "rate limit rid=%s attempt=%d sleep_s=%.2f exc=%s",
                        run_id, attempt, wait_s, type(e).__name__,
                    )
                    await asyncio.sleep(wait_s)
                    continue
                is_rate_limit = detect_rate_limit(e)
                log.exception(
                    "run failed rid=%s ticker=%s attempt=%d rate_limit=%s",
                    run_id, ticker, attempt, is_rate_limit,
                )
                storage.mark_run_status(run_id, status="failed", finished_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), error=f"{type(e).__name__}: {e}")
                events.emit(run_id, "run_failed", {
                    "reason": "rate_limited" if is_rate_limit else "exception",
                    "exception_class": type(e).__name__,
                    "message": str(e),
                    "traceback": _format_traceback(e),
                })
                return

        rj = storage.read_run(run_id)
        if rj and rj.get("cancel_requested"):
            storage.mark_run_status(run_id, status="failed", finished_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), error="cancelled")
            events.emit(run_id, "run_failed", {"reason": "cancelled"})
            return

        decision = (final_state or {}).get("decision") or {}
        action = decision.get("action")
        target = decision.get("target")
        rationale = decision.get("rationale", "")
        confidence = decision.get("confidence", 0.0)
        events.emit(run_id, "decision", {
            "action": action,
            "target": target,
            "rationale": rationale,
            "confidence": confidence,
        })
        storage.mark_run_status(
            run_id,
            status="done",
            finished_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            decision_action=action or "HOLD",
            decision_target=target,
            decision_rationale=rationale,
            decision_confidence=confidence,
        )
        queries_module.update_last_decision(
            ticker,
            run_id,
            f"{action} @ {target}" if target else (action or ""),
            datetime.now(timezone.utc),
        )
        duration_s = round(time.monotonic() - t_start, 2)
        summary_by_stage = {}
        if final_state:
            for stage_key, field in (
                ("market", "market_report"),
                ("sentiment", "sentiment_report"),
                ("news", "news_report"),
                ("fundamentals", "fundamentals_report"),
            ):
                excerpt = final_state.get(field) or ""
                if excerpt:
                    summary_by_stage[stage_key] = excerpt[:200]
        events.emit(run_id, "run_finished", {
            "duration_s": duration_s,
            "summary_by_stage": summary_by_stage,
        })
    finally:
        _active -= 1
        sem.release()


class _CancelSentinel(Exception):
    pass
