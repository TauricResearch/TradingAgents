"""Async orchestrator that wraps TradingAgentsGraph and emits typed events."""
from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
import traceback
from datetime import datetime, timezone
from typing import Optional

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

from web.server import db, events
from web.server.retry import compute_backoff, detect_rate_limit


log = logging.getLogger(__name__)

MAX_CONCURRENT = int(os.environ.get("TRADINGAGENTS_DASHBOARD_MAX_CONCURRENT", "3"))

# Retry policy. See docs/superpowers/specs/2026-06-02-rate-aware-retry-design.md
MAX_ATTEMPTS = 4
MAX_BACKOFF_S = 60.0


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
    t_start = time.monotonic()
    try:
        run = db.get_run(rid)
        if run is None:
            return
        if run.cancel_requested:
            db.mark_run_failed(rid, "cancelled")
            events.emit(rid, "run_failed", {"reason": "cancelled"})
            return

        events.emit(rid, "run_started", {"ticker": run.ticker})

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

        from web.server.callbacks import StreamingCallbackHandler
        handler = StreamingCallbackHandler(run_id=rid)
        graph = build_graph(callbacks=[handler])

        def _stage_summary_for_node(node_name: str, delta: dict):
            """Return (stage_key, summary, excerpt) for analyst_completed, or (None,...) to skip."""
            if node_name not in _STAGE_MAP:
                return (None, None, None)
            stage, report_field = _STAGE_MAP[node_name]
            excerpt = None
            if report_field:
                excerpt = (delta or {}).get(report_field, "")
                if excerpt and len(excerpt) > 200:
                    excerpt = excerpt[:200] + "\u2026"
            return (stage, "completed", excerpt)

        def cb(node_name: str, payload: dict) -> None:
            if db.get_run(rid).cancel_requested:
                raise _CancelSentinel()
            if node_name == "node_entered":
                events.emit(rid, "analyst_started", {"node": payload.get("node", node_name), **payload})
            elif node_name == "node_exited":
                stage, summary, excerpt = _stage_summary_for_node(
                    payload.get("node", ""), payload.get("delta", {})
                )
                if stage is None:
                    return  # tool/clear/portfolio_manager — no completion event
                data = {"stage": stage, "summary": summary}
                if excerpt:
                    data["report_excerpt"] = excerpt
                events.emit(rid, "analyst_completed", data)
            else:
                events.emit(rid, node_name, payload)

        loop = asyncio.get_event_loop()
        last_err = None
        trade_date = datetime.now(timezone.utc).date().isoformat()

        def _do_propagate():
            return graph.propagate(run.ticker, trade_date, event_callback=cb)

        for attempt in range(MAX_ATTEMPTS):
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
                if detect_rate_limit(e) and attempt < MAX_ATTEMPTS - 1:
                    wait_s = compute_backoff(attempt, e, max_s=MAX_BACKOFF_S)
                    events.emit(rid, "tool_call_warning", {
                        "message": f"rate limited; sleeping {wait_s:.1f}s before retry {attempt+1}/{MAX_ATTEMPTS-1}",
                        "retry_after_s": wait_s,
                        "exception_class": type(e).__name__,
                    })
                    log.warning(
                        "rate limit rid=%s attempt=%d sleep_s=%.2f exc=%s",
                        rid, attempt, wait_s, type(e).__name__,
                    )
                    await asyncio.sleep(wait_s)
                    continue
                is_rate_limit = detect_rate_limit(e)
                log.exception(
                    "run failed rid=%s ticker=%s attempt=%d rate_limit=%s",
                    rid, run.ticker, attempt, is_rate_limit,
                )
                db.mark_run_failed(rid, f"{type(e).__name__}: {e}")
                events.emit(rid, "run_failed", {
                    "reason": "rate_limited" if is_rate_limit else "exception",
                    "exception_class": type(e).__name__,
                    "message": str(e),
                    "traceback": _format_traceback(e),
                })
                return

        if db.get_run(rid).cancel_requested:
            db.mark_run_failed(rid, "cancelled")
            events.emit(rid, "run_failed", {"reason": "cancelled"})
            return

        # Emit the decision event before run_finished so the UI sees
        # them in chronological order.
        decision = (final or {}).get("decision") or {}
        action = decision.get("action")
        target = decision.get("target")
        rationale = decision.get("rationale", "")
        confidence = decision.get("confidence", 0.0)
        events.emit(rid, "decision", {
            "action": action,
            "target": target,
            "rationale": rationale,
            "confidence": confidence,
        })
        db.mark_run_done(
            rid,
            decision_action=action or "HOLD",
            decision_target=target,
            decision_rationale=rationale,
            decision_confidence=confidence,
        )
        db.update_watchlist_last_decision(
            run.ticker, rid,
            f"{action} @ {target}" if target else (action or ""),
            datetime.now(timezone.utc),
        )
        # Real duration + per-stage summary.
        duration_s = round(time.monotonic() - t_start, 2)
        summary_by_stage = {}
        if final:
            for stage_key, field in (
                ("market", "market_report"),
                ("sentiment", "sentiment_report"),
                ("news", "news_report"),
                ("fundamentals", "fundamentals_report"),
            ):
                excerpt = final.get(field) or ""
                if excerpt:
                    summary_by_stage[stage_key] = excerpt[:200]
        events.emit(rid, "run_finished", {
            "duration_s": duration_s,
            "summary_by_stage": summary_by_stage,
        })
    finally:
        _active -= 1
        sem.release()


class _CancelSentinel(Exception):
    pass
