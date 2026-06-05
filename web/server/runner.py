"""Async orchestrator that wraps TradingAgentsGraph and emits typed events."""
from __future__ import annotations

import asyncio
import logging
import os
import re
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
    # Portfolio Manager synthesises the risk debate and writes the
    # final decision into ``final_trade_decision``.  It is the
    # consolidator of the risk stage, so its exit must emit
    # ``analyst_completed`` with a report — otherwise the risk stage
    # never shows as "done" in the UI and the run is reported without
    # a final decision.
    "Portfolio Manager": ("risk", "final_trade_decision"),
}


# Map the framework's 5-tier rating (from ``signal_processing.parse_rating``)
# to the 3-tier action vocabulary the dashboard API and frontend speak.
_RATING_TO_ACTION = {
    "Buy": "BUY",
    "Overweight": "BUY",
    "Hold": "HOLD",
    "Underweight": "SELL",
    "Sell": "SELL",
}


# Heuristic confidence for each rating.  The framework's
# ``PortfolioDecision`` schema does not carry a numeric confidence
# field, so the runner derives one from the rating's strength.  This
# gives the dashboard a meaningful bar instead of an always-empty 0%.
_RATING_TO_CONFIDENCE = {
    "Buy": 0.9,
    "Overweight": 0.7,
    "Hold": 0.5,
    "Underweight": 0.3,
    "Sell": 0.1,
}


# Target-price extraction patterns, tried in order.  The structured
# ``**Price Target**: X`` field rendered from the PM's typed output is
# the most reliable signal, so it wins when present.  The model often
# puts the target inline in the decision header (``BUY at $4,000``)
# instead, so we fall back to that.  Both patterns require the
# currency sigil so position-sizing prose like ``at 3000 USD`` is not
# misread as a price target.
_TARGET_PATTERNS = (
    # Structured: "**Price Target**: 150.5" or "**Price Target**: $150.5"
    re.compile(r"\*\*Price Target\*\*\s*:\s*\$\s*([\d,.]+)|\*\*Price Target\*\*\s*:\s*([\d,.]+)"),
    # Inline in header: "BUY at $4,000" / "SELL at $2.50"
    re.compile(
        r"\b(?:Buy|Sell|Hold|Overweight|Underweight|BUY|SELL|HOLD|"
        r"OVERWEIGHT|UNDERWEIGHT)\s+at\s+\$\s*([\d,.]+)"
    ),
)


def _extract_target(markdown: str) -> Optional[float]:
    """Pull a numeric target price out of the PM's rendered markdown.

    Tries the structured ``**Price Target**: X`` field first, then
    falls back to ``ACTION at $X`` in the decision header.  Returns
    ``None`` if neither pattern matches — the model simply didn't
    emit a target (e.g. ``BUY MSTR`` with no number).
    """
    if not markdown:
        return None
    for pat in _TARGET_PATTERNS:
        m = pat.search(markdown)
        if not m:
            continue
        raw = next((g for g in m.groups() if g), None)
        if raw is None:
            continue
        try:
            return float(raw.replace(",", ""))
        except ValueError:
            continue
    return None


def _parse_pm_decision(final_state: dict, final_signal: str) -> dict:
    """Extract ``{action, target, rationale, confidence}`` for the dashboard.

    The Portfolio Manager's structured output is rendered to markdown
    and stored at ``final_state["final_trade_decision"]`` (see
    ``tradingagents.agents.schemas.render_pm_decision``).  The parsed
    5-tier rating is returned by ``TradingAgentsGraph.propagate`` as
    the second tuple element.  This helper turns those two inputs
    into the shape the API contract and ``DecisionPanel`` expect.
    """
    markdown = (final_state or {}).get("final_trade_decision", "") or ""
    action = _RATING_TO_ACTION.get(final_signal, "HOLD")
    confidence = _RATING_TO_CONFIDENCE.get(final_signal, 0.5)
    target = _extract_target(markdown)
    return {
        "action": action,
        "target": target,
        "rationale": markdown,
        "confidence": confidence,
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
_in_flight: set[str] = set()  # run_ids currently held by a worker task
_idle = threading.Event()
_idle.set()


def run_id_in_flight(run_id: str) -> bool:
    """True iff a worker task is currently processing ``run_id``."""
    return run_id in _in_flight


async def enqueue(
    ticker: str,
    date_str: str,
    force: bool = False,
    *,
    price_state: Optional["price_feed.PriceState"] = None,
) -> str:
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

    Keyword Args:
        price_state: optional live poller cache to snapshot the current
            ticker price at enqueue time.  If ``None`` (or if the
            snapshot is missing/stale/zero), ``start_price`` and
            ``start_price_at`` in ``run.json`` are left as ``None``.
    """
    ticker_u = ticker.upper()
    from web.server import price_feed as _pf  # local import to avoid cycles at import time

    existing = storage.find_resumable_run(ticker_u, date_str)
    if existing and not force:
        run_json = existing["run_json"]
        status = run_json.get("status")
        if status == "running":
            # Resume: reuse dir, enqueue the work. The framework's
            # thread_id is sha256(f"{ticker}:{date_str}") which is the
            # same as the prior partial's thread, so LangGraph's
            # SqliteSaver resumes from the last completed node.
            log.info("resuming run %s for %s", existing["run_id"], ticker_u)
            if run_id_in_flight(existing["run_id"]):
                log.info("resume already in flight for %s; no-op", existing["run_id"])
                return existing["run_id"]
            await _WORK_QUEUE.put(
                (existing["run_id"], ticker_u, date_str, existing["run_dir"])
            )
            return existing["run_id"]
        log.info("idempotent: returning existing %s run %s", status, existing["run_id"])
        return existing["run_id"]

    if existing and force:
        # Retire the partial before starting fresh.
        storage.mark_run_superseded(existing["run_id"])
        clear_today_checkpoint(ticker_u, date_str)
        log.info("force=true: superseded %s", existing["run_id"])

    # Snapshot the live poller's price (or None) so historical runs
    # record the price the user was looking at when they hit "Run".
    start_price: Optional[float] = None
    start_price_at: Optional[str] = None
    if price_state is not None:
        start_price, start_price_at = _pf.snapshot_price(price_state, ticker_u)

    info = storage.create_run_dir(
        ticker_u,
        llm_provider=DEFAULT_CONFIG.get("llm_provider"),
        deep_think_model=DEFAULT_CONFIG.get("deep_think_llm"),
        quick_think_model=DEFAULT_CONFIG.get("quick_think_llm"),
        start_price=start_price,
        start_price_at=start_price_at,
    )
    run_id = info["run_id"]
    # Enqueue a worker that calls _run_one.
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
            # Semaphore acquire failed; release the queue slot so
            # queue.join() can make progress if anyone calls it.
            _WORK_QUEUE.task_done()
            continue
        _active += 1
        _in_flight.add(run_id)
        task = asyncio.create_task(
            _run_one(run_id, ticker, date_str, run_dir, _sem)
        )
        # Always call task_done when the work has been consumed, and
        # clear the in-flight marker so a follow-up "Resume" click
        # knows the previous attempt has finished.
        def _on_done(t, _rid=run_id):
            _in_flight.discard(_rid)
            _WORK_QUEUE.task_done()
        task.add_done_callback(_on_done)


async def _run_one(run_id: str, ticker: str, date_str: str, run_dir: Path, sem: asyncio.Semaphore) -> None:
    """Execute a single run with file-based storage."""
    global _active
    t_start = time.monotonic()
    log.info("runner: run started rid=%s ticker=%s date=%s", run_id, ticker, date_str)
    try:
        run_json = storage.read_run(run_id)
        if run_json is None:
            return
        if run_json.get("cancel_requested"):
            storage.mark_run_status(
                run_id,
                status="failed",
                finished_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                error="cancelled",
                total_duration_s=round(time.monotonic() - t_start, 2),
            )
            events.emit(run_id, "run_failed", {"reason": "cancelled"})
            return

        events.emit(run_id, "run_started", {"ticker": ticker})

        from web.server.callbacks import CaptureCallbackHandler, StreamingCallbackHandler
        stream_handler = StreamingCallbackHandler(run_id=run_id)
        capture_handler = CaptureCallbackHandler(run_id=run_id, ticker=ticker)

        loop = asyncio.get_running_loop()

        config = {
            **DEFAULT_CONFIG,
            "ticker": ticker,
            "trade_date": date_str,
            "checkpoint_enabled": True,
        }
        graph = build_graph(config, callbacks=[stream_handler, capture_handler])

        # Per-node timing for structured stage progress logs.
        node_enter_t: dict[str, float] = {}

        def cb(node_name: str, payload: dict) -> None:
            rj = storage.read_run(run_id)
            if rj and rj.get("cancel_requested"):
                raise _CancelSentinel()
            if node_name == "node_entered":
                node = payload.get("node", node_name)
                node_enter_t[node] = time.monotonic()
                capture_handler.current_node = node
                log.info("runner: node_entered rid=%s node=%s", run_id, node)
                events.emit(run_id, "analyst_started", {"node": node, **payload})
            elif node_name == "node_exited":
                stage, summary, excerpt, full_text = _stage_summary_for_node(
                    payload.get("node", ""), payload.get("delta", {})
                )
                if stage is None:
                    return
                # Compute the per-stage duration so it can ride on the WS
                # event (the timeline renders it under the stage label).
                t_enter_for_event = node_enter_t.get(payload.get("node", ""))
                duration_ms_event = (
                    int((time.monotonic() - t_enter_for_event) * 1000) if t_enter_for_event else 0
                )
                data: dict = {"stage": stage, "summary": summary, "duration_ms": duration_ms_event}
                if excerpt:
                    data["report_excerpt"] = excerpt
                if full_text:
                    data["report_text"] = full_text
                events.emit(run_id, "analyst_completed", data)
                # Persist the stage result to disk.
                node = payload.get("node", "")
                stage_name = _STAGE_MAP.get(node, (node,))[0]
                t_enter = node_enter_t.pop(node, None)
                duration_ms = int((time.monotonic() - t_enter) * 1000) if t_enter else 0
                log.info(
                    "runner: node_exited rid=%s node=%s stage=%s duration_ms=%d",
                    run_id, node, stage_name, duration_ms,
                )
                storage.write_stage(
                    run_id,
                    stage_name,
                    {
                        "stage": stage_name,
                        "node": node,
                        "state_key": _state_key_for_node(node),
                        "completed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                        "duration_ms": duration_ms,
                        "value": summary,
                    },
                )
            else:
                events.emit(run_id, node_name, payload)

        def _do_propagate():
            return graph.propagate(ticker, date_str, event_callback=cb)

        final_state = None
        final_signal: str = ""
        for attempt in range(MAX_ATTEMPTS):
            try:
                final_state, final_signal = await loop.run_in_executor(None, _do_propagate)
                break
            except _CancelSentinel:
                storage.mark_run_status(
                    run_id,
                    status="failed",
                    finished_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    error="cancelled",
                    total_duration_s=round(time.monotonic() - t_start, 2),
                )
                events.emit(run_id, "run_failed", {"reason": "cancelled"})
                return
            except asyncio.CancelledError:
                storage.mark_run_status(
                    run_id,
                    status="failed",
                    finished_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    error="cancelled",
                    total_duration_s=round(time.monotonic() - t_start, 2),
                )
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
                storage.mark_run_status(
                    run_id,
                    status="failed",
                    finished_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    error=f"{type(e).__name__}: {e}",
                    total_duration_s=round(time.monotonic() - t_start, 2),
                )
                events.emit(run_id, "run_failed", {
                    "reason": "rate_limited" if is_rate_limit else "exception",
                    "exception_class": type(e).__name__,
                    "message": str(e),
                    "traceback": _format_traceback(e),
                })
                return

        rj = storage.read_run(run_id)
        if rj and rj.get("cancel_requested"):
            storage.mark_run_status(
                run_id,
                status="failed",
                finished_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                error="cancelled",
                total_duration_s=round(time.monotonic() - t_start, 2),
            )
            events.emit(run_id, "run_failed", {"reason": "cancelled"})
            return

        duration_s = round(time.monotonic() - t_start, 2)
        decision = _parse_pm_decision(final_state or {}, final_signal or "")
        action = decision["action"]
        target = decision["target"]
        rationale = decision["rationale"]
        confidence = decision["confidence"]
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
            total_duration_s=duration_s,
        )
        queries_module.update_last_decision(
            ticker,
            run_id,
            f"{action} @ {target}" if target else (action or ""),
            datetime.now(timezone.utc),
        )
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
        log.info(
            "runner: run finished rid=%s ticker=%s duration_s=%.2f action=%s target=%s",
            run_id, ticker, duration_s, action, target,
        )
    finally:
        _active -= 1
        sem.release()


class _CancelSentinel(Exception):
    pass
