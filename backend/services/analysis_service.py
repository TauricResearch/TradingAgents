"""Wraps TradingAgentsGraph so FastAPI can run it without blocking the event loop.

Uses ``TradingAgentsGraph.async_propagate()`` directly — no asyncio.to_thread
wrapper around the entire propagate call.  Individual blocking operations
(graph.invoke, file I/O, memory log) are off-loaded inside async_propagate
itself, so the FastAPI event loop stays free throughout the run.
"""
import asyncio
import logging
import sys
import os
import time
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.websocket import ws_manager
from backend.models.analysis import AnalysisResult
from backend.models.settings import AppSettings

_logger = logging.getLogger(__name__)

# Ensure project root is importable when running from the web layer
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# Report fields that are streamed to the browser via WebSocket.
# Use StateKeys once the package import is resolved at call time.
_REPORT_FIELDS = (
    "market_report", "sentiment_report", "news_report", "fundamentals_report",
    "macro_report", "options_report", "quant_report", "earnings_report",
    "review_report", "investment_plan", "trader_investment_plan", "final_trade_decision",
)


def _build_config(settings: AppSettings) -> dict:
    """Convert AppSettings → TradingAgentsGraph-compatible config dict."""
    cfg: dict = {
        "llm_provider": settings.llm_provider,
        "deep_think_llm": settings.deep_think_llm,
        "quick_think_llm": settings.quick_think_llm,
        "max_debate_rounds": settings.max_debate_rounds,
        "max_risk_discuss_rounds": settings.max_risk_rounds,
        "output_language": getattr(settings, "output_language", "English") or "English",
        "analyst_concurrency_limit": getattr(settings, "analyst_concurrency_limit", 1) or 1,
        "data_vendors": {
            "core_stock_apis": settings.active_data_vendor,
            "technical_indicators": settings.active_data_vendor,
            "fundamental_data": settings.active_data_vendor,
            "news_data": settings.active_data_vendor,
        },
    }
    # Optional: custom API base URL (for Ollama, LiteLLM, etc.)
    if getattr(settings, "backend_url", None):
        cfg["backend_url"] = settings.backend_url
    # Provider-specific reasoning effort/thinking level
    if getattr(settings, "openai_reasoning_effort", None):
        cfg["openai_reasoning_effort"] = settings.openai_reasoning_effort
    if getattr(settings, "anthropic_effort", None):
        cfg["anthropic_effort"] = settings.anthropic_effort
    if getattr(settings, "google_thinking_level", None):
        cfg["google_thinking_level"] = settings.google_thinking_level
    return cfg


def _extract_stats(callbacks: list) -> dict:
    """Pull token / call counts from StatsCallbackHandler."""
    try:
        from cli.stats_handler import StatsCallbackHandler
        for cb in callbacks:
            if isinstance(cb, StatsCallbackHandler):
                return cb.get_stats()
    except Exception:
        pass
    return {"llm_calls": 0, "tool_calls": 0, "tokens_in": 0, "tokens_out": 0}


async def run_analysis(
    ticker: str,
    trade_date: str,
    asset_type: str,
    settings: AppSettings,
    db: AsyncSession,
    triggered_by: str = "manual",
) -> tuple[str, AnalysisResult]:
    """Run a full TradingAgents analysis and stream progress via WebSocket.

    Uses ``async_propagate()`` so the event loop is free during LLM / tool calls.
    WS events are emitted in real time by patching ``graph.stream`` — the same
    approach as before, but now inside an async context without a thread wrapper.

    Returns
    -------
    tuple[str, AnalysisResult]
        ``(task_id, db_row)``
    """
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    task_id = str(uuid.uuid4())
    _logger.info("Starting analysis task=%s ticker=%s date=%s", task_id, ticker, trade_date)

    await ws_manager.send(task_id, {"type": "status", "status": "starting", "agent": "Initializing"})

    # Collect WS events produced during propagation
    events: list[dict] = []

    callbacks = []
    try:
        from cli.stats_handler import StatsCallbackHandler
        callbacks = [StatsCallbackHandler()]
    except ImportError:
        pass

    config = _build_config(settings)
    ta = TradingAgentsGraph(
        selected_analysts=settings.selected_analysts,
        debug=False,
        config=config,
        callbacks=callbacks,
    )

    # Patch graph.stream so intermediate state updates are captured as WS events.
    # This runs inside asyncio.to_thread (inside async_propagate), so appending
    # to a list is safe — no cross-thread mutation of shared state.
    original_invoke = ta.graph.invoke

    def _patched_invoke(state, config_arg=None, **kwargs):
        # We still need streaming for WS events; run stream internally
        prev_state: dict = {}
        final: dict = {}
        for chunk in ta.graph.stream(state, config_arg or {}, **kwargs):
            for key, value in chunk.items():
                if key in _REPORT_FIELDS and value and value != prev_state.get(key):
                    events.append({"type": "report", "section": key, "content": value})
                    prev_state[key] = value
            final.update(chunk)
        return final

    ta.graph.invoke = _patched_invoke

    start = time.time()
    try:
        final_state, signal = await ta.async_propagate(ticker, trade_date, asset_type)
        stats = _extract_stats(callbacks)

        # Broadcast captured report events
        for event in events:
            await ws_manager.send(task_id, event)

        duration = time.time() - start

        # Persist to DB using PropagateResult for type-safe field access
        from tradingagents.agents.schemas import PropagateResult
        result = PropagateResult.from_state(final_state, signal)

        row = AnalysisResult(
            ticker=ticker,
            trade_date=trade_date,
            asset_type=asset_type,
            signal=result.signal,
            market_report=result.market_report,
            sentiment_report=result.sentiment_report,
            news_report=result.news_report,
            fundamentals_report=result.fundamentals_report,
            macro_report=result.macro_report,
            options_report=result.options_report,
            quant_report=result.quant_report,
            earnings_report=result.earnings_report,
            review_report=result.review_report,
            investment_plan=result.investment_plan,
            trader_plan=result.trader_plan,
            final_decision=result.final_decision,
            llm_calls=stats.get("llm_calls", 0),
            tool_calls=stats.get("tool_calls", 0),
            tokens_in=stats.get("tokens_in", 0),
            tokens_out=stats.get("tokens_out", 0),
            duration_seconds=duration,
            triggered_by=triggered_by,
        )
        db.add(row)
        await db.flush()

        await ws_manager.send(task_id, {
            "type": "decision",
            "signal": signal,
            "final_decision": result.final_decision,
        })
        await ws_manager.send(task_id, {
            "type": "complete",
            "analysis_id": row.id,
            "duration_seconds": round(duration, 2),
            "llm_calls": stats.get("llm_calls", 0),
        })

        return task_id, row

    except Exception as exc:
        _logger.error("Analysis failed task=%s: %s", task_id, exc, exc_info=True)
        await ws_manager.send(task_id, {"type": "error", "message": str(exc)})
        raise
    finally:
        await ws_manager.close_task(task_id)
