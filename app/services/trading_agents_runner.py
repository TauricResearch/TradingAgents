"""
Orchestrator that wraps TauricResearch/TradingAgents for the
trading-agents-service.

This is the trading-specific service layer — bridges between the
generic FastAPI/DB/queue/observability infrastructure (template-grade)
and the trading-firm-specific TradingAgents library (NOT template-grade).
Per the TT-182 discipline rule, app-specific code lives here, not in
foundational layers.

Flow:
  1. `run_analysis(run_id, ...)` is the public entry point
  2. Marks the `runs` row as `running`
  3. Constructs a TradingAgentsGraph with file-based memory disabled
     (we capture state ourselves via the LangChain callback)
  4. Async-streams the LangGraph workflow with a RunRecorderHandler
     callback that writes each agent's output to `agent_reports`
     + publishes to Redis pub-sub for live SSE
  5. After completion, writes the final BUY/SELL/HOLD verdict to
     `decisions`
  6. Marks the run `complete` (or `failed` on error)
  7. Sends a DONE_SENTINEL on the pub-sub channel so SSE consumers
     close cleanly

Failures are captured to Sentry + recorded in the run row's metadata.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import sentry_sdk
from sqlalchemy import update
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings
from app.db import asyncpg_url
from app.models import Decision, Run
from app.services.callbacks import RunRecorderHandler
from app.services.pubsub import publish_done, publish_event


logger = logging.getLogger(__name__)


async def run_analysis(
    run_id: str,
    user_id: str,
    ticker: str,
    trade_date: str,
) -> None:
    """
    Run one TradingAgents analysis for `ticker` on `trade_date`. Drives
    DB state + pub-sub for the lifetime of the run. Catches all errors —
    raising here would orphan the run row in `running` state.

    Invoked from `POST /analyze`'s FastAPI BackgroundTasks.
    """
    # TT-298: per-run engine. The global singleton engine was created
    # at FastAPI startup on the request handler's event loop. This
    # BackgroundTask runs in a different loop context — every DB op
    # through the singleton threw "Future attached to a different loop"
    # and cascaded into chain errors + runaway retry loops.
    #
    # Creating the engine HERE binds it to this BackgroundTask's loop.
    # All downstream DB ops (status updates, agent_reports persist via
    # the callback handler, decision write, settlement) flow through
    # this sessionmaker and stay on the same loop.
    #
    # Cost: ~1 TCP+TLS handshake to Neon per run (pool warmup), then
    # 5 connections shared across ~12 agents. Disposed in `finally` so
    # the connection pool is cleanly returned to Neon at run-end.
    url, connect_args = asyncpg_url(settings.DATABASE_URL)
    engine = create_async_engine(
        url,
        connect_args=connect_args,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )
    sessionmaker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    await _set_run_status(sessionmaker, run_id, "running")
    await publish_event(
        run_id,
        {
            "type": "run_started",
            "ticker": ticker,
            "trade_date": trade_date,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )

    try:
        decision_text = await _execute_pipeline(run_id, ticker, trade_date, sessionmaker)
        await _persist_decision(sessionmaker, run_id, decision_text)
        await _set_run_status(sessionmaker, run_id, "complete", completed=True)
        await publish_event(
            run_id,
            {
                "type": "run_complete",
                "decision": decision_text,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception as e:
        # Capture full exception to Sentry (tagged with app:lyceum-fund via
        # the global observability init).
        sentry_sdk.capture_exception(e)
        logger.exception("analysis failed for run %s ticker %s", run_id, ticker)
        await _set_run_status(sessionmaker, run_id, "failed", completed=True)
        await publish_event(
            run_id,
            {
                "type": "run_error",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
    finally:
        # Always send done so SSE subscribers close cleanly.
        await publish_done(run_id)
        # TT-298: dispose the per-run engine so its connection pool
        # is cleanly returned. Outstanding fire-and-forget tasks that
        # haven't checked out a connection yet will fail their writes
        # (logged + swallowed via _log_task_exception) — acceptable
        # since the run itself is complete and pure-metadata-update is
        # best-effort enrichment.
        try:
            await engine.dispose()
        except Exception as e:
            logger.warning("per-run engine dispose failed for %s: %s", run_id, e)


async def _execute_pipeline(
    run_id: str,
    ticker: str,
    trade_date: str,
    sessionmaker,
) -> str:
    """
    Run the TradingAgents LangGraph pipeline. Returns the final trade
    decision string (BUY/SELL/HOLD with rationale).

    Bypasses TradingAgents.propagate() so we control the stream loop
    and can inject our own callback. Replicates propagate()'s minimal
    setup — past_context injection + init state + graph args.
    """
    # Import here so the module loads cleanly even when TradingAgents
    # transitive deps are slow to resolve (helps unit tests).
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    # Build config:
    # - memory_log_path=None disables the upstream file-based memory log
    #   (we capture state via callbacks instead)
    # - checkpoint_enabled=False keeps it simple for v1; we don't need
    #   resume-from-step yet
    cfg = _build_config()
    ta = TradingAgentsGraph(debug=False, config=cfg)

    # Mirror what _run_graph does for state init.
    past_context = ta.memory_log.get_past_context(ticker)  # returns "" when memory disabled
    init_state = ta.propagator.create_initial_state(
        ticker, trade_date, past_context=past_context
    )
    args = ta.propagator.get_graph_args() or {}

    # Inject our callback so every agent's output flows to DB + pub-sub.
    handler = RunRecorderHandler(run_id=run_id, sessionmaker=sessionmaker)
    args.setdefault("config", {}).setdefault("callbacks", []).append(handler)

    # astream yields per-node deltas. We merge them into final_state for
    # the terminal decision extraction. The callback handles per-step
    # persistence + pub-sub independently.
    final_state: dict = {}
    async for chunk in ta.graph.astream(init_state, **args):
        if isinstance(chunk, dict):
            final_state.update(chunk)

    decision = final_state.get("final_trade_decision") or "(no decision returned)"
    return str(decision)


def _build_config() -> dict:
    """
    TradingAgents config dict. Critical settings:
      - memory_log_path=None disables file-based memory; we capture via
        LangChain callbacks instead.
      - checkpoint_enabled=False — v1 doesn't need resume.
      - LLM provider keys come from process env (OPENAI_API_KEY); the
        TradingAgents factory reads these directly.
    """
    from tradingagents.default_config import DEFAULT_CONFIG

    cfg = dict(DEFAULT_CONFIG)
    cfg["memory_log_path"] = None
    cfg["checkpoint_enabled"] = False
    # OPENAI_API_KEY is read from environment by TradingAgents directly —
    # nothing to inject here. Pydantic-settings already loaded it.
    return cfg


async def _set_run_status(
    sessionmaker,
    run_id: str,
    status: str,
    *,
    completed: bool = False,
) -> None:
    """Update a run row's status. Always non-fatal — logs on failure."""
    async with sessionmaker() as session:
        try:
            values: dict = {"status": status}
            if completed:
                values["completed_at"] = datetime.now(timezone.utc)
            await session.execute(
                update(Run).where(Run.id == run_id).values(**values)
            )
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.warning("run-status update failed for %s → %s: %s", run_id, status, e)


async def _persist_decision(sessionmaker, run_id: str, decision_text: str) -> None:
    """Write the final BUY/SELL/HOLD decision row."""
    async with sessionmaker() as session:
        try:
            session.add(
                Decision(
                    run_id=run_id,
                    decision=_extract_action(decision_text),
                    rationale=decision_text,
                )
            )
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.warning("decision persist failed for %s: %s", run_id, e)


def _extract_action(decision_text: str) -> str:
    """
    Best-effort BUY/SELL/HOLD extraction. TradingAgents' final
    `final_trade_decision` is typically a paragraph; the keyword
    near the top of the response is reliable. Falls back to HOLD if
    nothing matches.
    """
    upper = (decision_text or "")[:500].upper()
    for action in ("BUY", "SELL", "HOLD"):
        if action in upper:
            return action
    return "HOLD"
