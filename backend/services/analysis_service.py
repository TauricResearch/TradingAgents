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

# ── Redirect ALL trading_agents file I/O to temp BEFORE first import ──────────
import tempfile as _tf
_TMP = _tf.gettempdir()
os.environ.setdefault("TRADINGAGENTS_RESULTS_DIR",      os.path.join(_TMP, "ta_results"))
os.environ.setdefault("TRADINGAGENTS_DATA_CACHE_DIR",   os.path.join(_TMP, "ta_cache"))
os.environ.setdefault("TRADINGAGENTS_MEMORY_LOG_PATH",  os.path.join(_TMP, "ta_memory.md"))
os.environ.setdefault("TRADINGAGENTS_LOG_DIR",          _TMP)  # covers logging_config.py
# ──────────────────────────────────────────────────────────────────────────────

# Running task registry — used for cancellation
_RUNNING_TASKS: dict[str, asyncio.Task] = {}

# Report fields that are streamed to the browser via WebSocket.
# Use StateKeys once the package import is resolved at call time.
_REPORT_FIELDS = (
    "market_report", "sentiment_report", "news_report", "fundamentals_report",
    "macro_report", "options_report", "quant_report", "earnings_report",
    "review_report", "investment_plan", "trader_investment_plan", "final_trade_decision",
)


async def _get_historical_analyses_context(
    ticker: str, trade_date: str, db: AsyncSession, limit: int = 5
) -> str:
    """Önceki DB analizlerini past_context için markdown formatında döndürür."""
    from sqlalchemy import select, desc as _desc

    result = await db.execute(
        select(AnalysisResult)
        .where(AnalysisResult.ticker == ticker)
        .where(AnalysisResult.trade_date < trade_date)
        .order_by(_desc(AnalysisResult.created_at))
        .limit(limit)
    )
    rows = result.scalars().all()
    if not rows:
        return ""

    parts = [f"=== {ticker} GEÇMİŞ ANALİZ RAPORLARI ===\n"]
    for row in reversed(rows):  # kronolojik sıra
        parts.append(f"--- Tarih: {row.trade_date} | Sinyal: {row.signal or 'N/A'} ---")
        for label, field in [
            ("Piyasa Raporu", row.market_report),
            ("Haber Raporu", row.news_report),
            ("Temel Analiz", row.fundamentals_report),
            ("Son Karar", row.final_decision),
        ]:
            if field and field.strip():
                parts.append(f"{label}:\n{field[:400].strip()}...")
        parts.append("")
    return "\n".join(parts)


def _build_config(settings: AppSettings) -> dict:
    """Convert AppSettings → TradingAgentsGraph-compatible config dict."""
    from tradingagents.graph.trading_graph import DEFAULT_CONFIG

    import tempfile, os as _os
    _tmp = tempfile.gettempdir()
    cfg: dict = {
        # Redirect all file I/O to temp — DB is the source of truth
        "data_cache_dir": _os.path.join(_tmp, "ta_cache"),
        "results_dir":    _os.path.join(_tmp, "ta_results"),
        "memory_log_path": _os.path.join(_tmp, "ta_memory.md"),
        # LLM
        "llm_provider": settings.llm_provider,
        "deep_think_llm": settings.deep_think_llm,
        "quick_think_llm": settings.quick_think_llm,
        # Debate / graph behaviour
        "max_debate_rounds": settings.max_debate_rounds,
        "max_risk_discuss_rounds": settings.max_risk_rounds,
        "output_language": settings.output_language or "English",
        "analyst_concurrency_limit": settings.analyst_concurrency_limit or 1,
        "skip_disk_log": True,   # DB is source of truth; skip redundant JSON writes
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


def _extract_stats(handler) -> dict:
    """Return token / call counts from a StatsCallbackHandler instance."""
    try:
        return handler.get_stats()
    except Exception:
        return {"llm_calls": 0, "tool_calls": 0, "tokens_in": 0, "tokens_out": 0}


async def cancel_analysis(task_id: str) -> bool:
    """Cancel a running analysis task. Returns True if found and cancelled."""
    task = _RUNNING_TASKS.pop(task_id, None)
    if task and not task.done():
        task.cancel()
        return True
    return False


async def run_analysis(
    ticker: str,
    trade_date: str,
    asset_type: str,
    settings: AppSettings,
    db: AsyncSession,
    triggered_by: str = "manual",
    task_id: str | None = None,
) -> tuple[str, AnalysisResult]:
    """Run a full TradingAgents analysis and stream progress via WebSocket.

    ``task_id`` should be passed from the API handler so the WS channel matches
    what the client connected to. If omitted a new UUID is generated (e.g. cron).

    Returns
    -------
    tuple[str, AnalysisResult]
        ``(task_id, db_row)``
    """
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    if task_id is None:
        task_id = str(uuid.uuid4())

    # Register this asyncio Task so it can be cancelled externally
    current = asyncio.current_task()
    if current:
        _RUNNING_TASKS[task_id] = current

    _logger.info("Starting analysis task=%s ticker=%s date=%s", task_id, ticker, trade_date)

    await ws_manager.send(task_id, {"type": "status", "status": "starting", "agent": "Initializing"})

    # Backend-local imports (kept out of module top so the tradingagents env
    # redirect above always runs before anything pulls in the package).
    from backend.services.stats_handler import StatsCallbackHandler
    from backend.core.catalog import node_progress

    # The graph runs in a worker thread (asyncio.to_thread). Capture the loop
    # now so that thread can push live progress/report events back over the WS.
    loop = asyncio.get_running_loop()

    def _emit(event: dict) -> None:
        """Thread-safe, fire-and-forget WS send from the graph worker thread."""
        try:
            asyncio.run_coroutine_threadsafe(ws_manager.send(task_id, event), loop)
        except Exception:
            pass

    stats_handler = StatsCallbackHandler()

    start = time.time()
    try:
        # Build config and construct graph INSIDE the try so any failure
        # (missing API key, bad config, import error) reaches the WS error handler.
        await ws_manager.send(task_id, {"type": "status", "status": "starting", "agent": "LLM istemcisi hazırlanıyor..."})
        config = _build_config(settings)
        if getattr(settings, "include_historical_analyses", False):
            hist_ctx = await _get_historical_analyses_context(ticker, trade_date, db)
            if hist_ctx:
                config["historical_context"] = hist_ctx
        ta = TradingAgentsGraph(
            selected_analysts=settings.selected_analysts,
            debug=False,
            config=config,
        )

        # Patch graph.invoke so we can (a) stream live progress, (b) stream
        # report sections as they are produced, and (c) attach the stats handler
        # to the run config. Streaming with both modes gives us "updates" (which
        # node just ran → progress label) and "values" (full cumulative state →
        # report sections + the final state to persist).
        def _patched_invoke(state, config_arg=None, **kwargs):
            if config_arg is not None and "config" not in kwargs:
                kwargs["config"] = config_arg
            kwargs.pop("stream_mode", None)  # we set the modes explicitly below
            cfg = dict(kwargs.pop("config", None) or {})
            # Run-config callbacks propagate to every nested LLM + tool call, so
            # one handler captures the whole run without double counting.
            cfg["callbacks"] = list(cfg.get("callbacks") or []) + [stats_handler]

            prev_state: dict = {}
            final: dict = {}
            for mode, chunk in ta.graph.stream(
                state, stream_mode=["updates", "values"], config=cfg, **kwargs
            ):
                if mode == "updates":
                    for node_name in (chunk or {}):
                        prog = node_progress(node_name)
                        if prog:
                            _emit(prog)
                else:  # "values": full cumulative state
                    for key, value in chunk.items():
                        if key in _REPORT_FIELDS and value and value != prev_state.get(key):
                            _emit({"type": "report", "section": key, "content": value})
                            prev_state[key] = value
                    final = chunk
            return final

        ta.graph.invoke = _patched_invoke

        final_state, signal = await ta.async_propagate(ticker, trade_date, asset_type)
        stats = _extract_stats(stats_handler)

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

    except asyncio.CancelledError:
        _logger.info("Analysis cancelled task=%s", task_id)
        await ws_manager.send(task_id, {"type": "error", "message": "Analiz iptal edildi."})
        raise
    except Exception as exc:
        _logger.error("Analysis failed task=%s: %s", task_id, exc, exc_info=True)
        await ws_manager.send(task_id, {"type": "error", "message": str(exc)})
        raise
    finally:
        _RUNNING_TASKS.pop(task_id, None)
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
    from backend.core.database import AsyncSessionLocal

    config = _build_config(settings)
    concurrency = settings.analyst_concurrency_limit or 1

    # Run each ticker — respect analyst_concurrency_limit for parallel runs
    semaphore = asyncio.Semaphore(concurrency)

    async def _run_one(ticker: str):
        async with semaphore:
            _logger.info("Portfolio analysis: running %s", ticker)
            # Each concurrent ticker gets its OWN session: an AsyncSession is
            # not safe for use by multiple coroutines at once, and the previous
            # shared-session version raced under concurrency_limit > 1.
            async with AsyncSessionLocal() as t_db:
                _, row = await run_analysis(ticker, trade_date, asset_type, settings, t_db, triggered_by)
                # Capture primitives before commit so nothing depends on the
                # session/ORM identity once this coroutine returns.
                data = {
                    "id": row.id,
                    "trader_plan": row.trader_plan,
                    "portfolio_decision": row.final_decision,
                }
                await t_db.commit()
            return ticker, data

    results = await asyncio.gather(*[_run_one(t.upper()) for t in tickers], return_exceptions=True)

    ticker_reports: dict = {}
    analysis_ids: list[int] = []
    for res in results:
        if isinstance(res, Exception):
            _logger.warning("Portfolio ticker run failed: %s", res)
            continue
        ticker, data = res
        analysis_ids.append(data["id"])
        ticker_reports[ticker] = {
            "trader_plan": data["trader_plan"],
            "portfolio_decision": data["portfolio_decision"],
        }

    # Build SuperPortfolioManager node from a fresh graph instance
    super_report = ""
    if ticker_reports:
        try:
            ta = TradingAgentsGraph(
                selected_analysts=settings.selected_analysts,
                debug=False,
                config=config,
            )
            from tradingagents.agents.managers.super_portfolio_manager import create_super_portfolio_manager
            # The graph stores the deep-think LLM as deep_thinking_llm (there is
            # no deep_client attribute). Run the (blocking) LLM call off-loop.
            spm_node = create_super_portfolio_manager(ta.deep_thinking_llm)
            state_out = await asyncio.to_thread(spm_node, {"ticker_reports": ticker_reports})
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
