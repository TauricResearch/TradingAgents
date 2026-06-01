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
    from tradingagents.graph.trading_graph import DEFAULT_CONFIG

    cfg: dict = {
        # Inherit path defaults from the library so the graph never KeyErrors
        "data_cache_dir": DEFAULT_CONFIG.get("data_cache_dir"),
        "results_dir": DEFAULT_CONFIG.get("results_dir"),
        # LLM
        "llm_provider": settings.llm_provider,
        "deep_think_llm": settings.deep_think_llm,
        "quick_think_llm": settings.quick_think_llm,
        # Debate / graph behaviour
        "max_debate_rounds": settings.max_debate_rounds,
        "max_risk_discuss_rounds": settings.max_risk_rounds,
        "output_language": settings.output_language or "English",
        "analyst_concurrency_limit": settings.analyst_concurrency_limit or 1,
        "checkpoint_enabled": getattr(settings, "checkpoint_enabled", False),
        "max_recur_limit": getattr(settings, "max_recur_limit", 1000) or 1000,
        # News fetching
        "news_article_limit": getattr(settings, "news_article_limit", 20) or 20,
        "global_news_article_limit": getattr(settings, "global_news_article_limit", 10) or 10,
        "global_news_lookback_days": getattr(settings, "global_news_lookback_days", 7) or 7,
        # Per-category vendor routing (replaces single active_data_vendor)
        "data_vendors": {
            "core_stock_apis": getattr(settings, "data_vendor_core_stock", None) or settings.active_data_vendor,
            "technical_indicators": getattr(settings, "data_vendor_technicals", None) or settings.active_data_vendor,
            "fundamental_data": getattr(settings, "data_vendor_fundamentals", None) or settings.active_data_vendor,
            "news_data": getattr(settings, "data_vendor_news", None) or settings.active_data_vendor,
        },
    }
    # Optional fields — only add when set to avoid overriding library defaults
    if getattr(settings, "backend_url", None):
        cfg["backend_url"] = settings.backend_url
    if getattr(settings, "benchmark_ticker", None):
        cfg["benchmark_ticker"] = settings.benchmark_ticker
    if getattr(settings, "azure_deployment", None):
        cfg["azure_deployment_name"] = settings.azure_deployment
    # Provider-specific reasoning effort/thinking level
    if getattr(settings, "openai_reasoning_effort", None):
        cfg["openai_reasoning_effort"] = settings.openai_reasoning_effort
    if getattr(settings, "anthropic_effort", None):
        cfg["anthropic_effort"] = settings.anthropic_effort
    if getattr(settings, "google_thinking_level", None):
        cfg["google_thinking_level"] = settings.google_thinking_level
    return cfg


def _history_json_from(value) -> str:
    """Serialize a debate history value (list, dict, or str) to JSON string."""
    import json as _json
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return _json.dumps(value, ensure_ascii=False)
    return str(value)


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

        inv_debate = final_state.get("investment_debate_state", {}) or {}
        risk_debate = final_state.get("risk_debate_state", {}) or {}

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
            bull_history=_history_json_from(inv_debate.get("bull_history", "")),
            bear_history=_history_json_from(inv_debate.get("bear_history", "")),
            investment_debate_history=_history_json_from(inv_debate.get("history", "")),
            risk_debate_history=_history_json_from(risk_debate.get("history", "")),
            judge_decision=str(inv_debate.get("judge_decision", "") or ""),
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


async def run_portfolio_analysis(
    tickers: list[str],
    trade_date: str,
    asset_type: str,
    settings: AppSettings,
    db: AsyncSession,
    triggered_by: str = "manual",
):
    """Run individual analyses for each ticker then synthesize via SuperPortfolioManager.

    Returns the saved MultiTickerAnalysis row.
    """
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from backend.models.portfolio_analysis import MultiTickerAnalysis

    config = _build_config(settings)
    concurrency = settings.analyst_concurrency_limit or 1

    # Run each ticker — respect analyst_concurrency_limit for parallel runs
    semaphore = asyncio.Semaphore(concurrency)

    async def _run_one(ticker: str):
        async with semaphore:
            _logger.info("Portfolio analysis: running %s", ticker)
            _, row = await run_analysis(ticker, trade_date, asset_type, settings, db, triggered_by)
            return ticker, row

    results = await asyncio.gather(*[_run_one(t.upper()) for t in tickers], return_exceptions=True)

    ticker_reports: dict = {}
    analysis_ids: list[int] = []
    for res in results:
        if isinstance(res, Exception):
            _logger.warning("Portfolio ticker run failed: %s", res)
            continue
        ticker, row = res
        analysis_ids.append(row.id)
        ticker_reports[ticker] = {
            "trader_plan": row.trader_plan,
            "portfolio_decision": row.final_decision,
        }

    # Build SuperPortfolioManager node from a fresh graph instance
    super_report = ""
    if ticker_reports:
        try:
            callbacks = []
            try:
                from cli.stats_handler import StatsCallbackHandler
                callbacks = [StatsCallbackHandler()]
            except ImportError:
                pass

            ta = TradingAgentsGraph(
                selected_analysts=settings.selected_analysts,
                debug=False,
                config=config,
                callbacks=callbacks,
            )
            from tradingagents.agents.managers.super_portfolio_manager import create_super_portfolio_manager
            spm_node = create_super_portfolio_manager(ta.deep_client)
            state_out = spm_node({"ticker_reports": ticker_reports})
            super_report = state_out.get("super_portfolio_report", "")
        except Exception as e:
            _logger.error("SuperPortfolioManager failed: %s", e, exc_info=True)
            super_report = f"Portfolio synthesis failed: {e}"

    multi_row = MultiTickerAnalysis(
        trade_date=trade_date,
        asset_type=asset_type,
        super_portfolio_report=super_report,
        triggered_by=triggered_by,
    )
    multi_row.tickers = tickers
    multi_row.analysis_ids = analysis_ids
    db.add(multi_row)
    await db.flush()
    return multi_row
