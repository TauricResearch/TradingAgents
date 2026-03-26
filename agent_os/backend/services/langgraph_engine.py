import asyncio
import datetime as _dt
import json
import logging
import time
from pathlib import Path
from typing import Dict, Any, AsyncGenerator
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.graph.scanner_graph import ScannerGraph
from tradingagents.graph.portfolio_graph import PortfolioGraph
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.report_paths import get_market_dir, get_ticker_dir, get_daily_dir, generate_flow_id, generate_run_id
from tradingagents.portfolio.report_store import ReportStore
from tradingagents.portfolio.store_factory import create_report_store
from tradingagents.daily_digest import append_to_digest
from tradingagents.agents.utils.json_utils import extract_json
from tradingagents.observability import RunLogger, set_run_logger

logger = logging.getLogger("agent_os.engine")

# ---------------------------------------------------------------------------
# LLM policy / 404 error helpers
# ---------------------------------------------------------------------------

def _is_policy_error(exc: Exception) -> bool:
    """Return True if *exc* is a provider 404 / guardrail / policy error."""
    if getattr(exc, "status_code", None) == 404:
        return True
    cause = getattr(exc, "__cause__", None)
    if getattr(cause, "status_code", None) == 404:
        return True
    # Catch RuntimeErrors wrapped by tool_runner
    msg = str(exc).lower()
    return "404" in msg and ("policy" in msg or "guardrail" in msg or "openrouter" in msg)


def _build_fallback_config(config: dict) -> "dict | None":
    """Return config with per-tier fallback models substituted, or None if none set."""
    tiers = ("quick_think", "mid_think", "deep_think")
    replacements: dict = {}
    for tier in tiers:
        fb_llm = config.get(f"{tier}_fallback_llm")
        fb_prov = config.get(f"{tier}_fallback_llm_provider")
        if fb_llm:
            replacements[f"{tier}_llm"] = fb_llm
        if fb_prov:
            replacements[f"{tier}_llm_provider"] = fb_prov
    if not replacements:
        return None
    return {**config, **replacements}

# Maximum characters of prompt/response content to include in the short message
_MAX_CONTENT_LEN = 300


def _fetch_prices(tickers: list[str]) -> dict[str, float]:
    """Fetch the latest closing price for each ticker via yfinance.

    Returns a dict of {ticker: price}.  Tickers that fail are silently skipped.
    """
    if not tickers:
        return {}
    try:
        import yfinance as yf
        data = yf.download(tickers, period="2d", auto_adjust=True, progress=False, threads=True)
        if data.empty:
            return {}
        close = data["Close"] if "Close" in data.columns else data
        # Take the last available row
        last_row = close.iloc[-1]
        return {
            t: float(last_row[t])
            for t in tickers
            if t in last_row.index and not __import__("math").isnan(last_row[t])
        }
    except Exception as exc:
        logger.warning("_fetch_prices failed: %s", exc)
        return {}


def _tickers_from_decision(decision: dict) -> list[str]:
    """Extract all ticker symbols referenced in a PM decision dict."""
    tickers = set()
    for key in ("sells", "buys", "holds"):
        for item in decision.get(key) or []:
            if isinstance(item, dict):
                t = item.get("ticker") or item.get("symbol")
            else:
                t = str(item)
            if t:
                tickers.add(t.upper())
    return list(tickers)

# Maximum characters of prompt/response for the full fields (generous limit)
_MAX_FULL_LEN = 50_000

# Keywords in tool output that indicate the error was handled gracefully
_GRACEFUL_SKIP_KEYWORDS = ("gracefully", "fallback", "skipped")

# ──────────────────────────────────────────────────────────────────────────────
# Tool-name → primary service mapping (best-effort, used for display only)
# ──────────────────────────────────────────────────────────────────────────────
_TOOL_SERVICE_MAP: Dict[str, str] = {
    # Core stock APIs
    "get_stock_data": "yfinance",
    "get_indicators": "yfinance",
    # Fundamental data
    "get_fundamentals": "yfinance",
    "get_balance_sheet": "yfinance",
    "get_cashflow": "yfinance",
    "get_income_statement": "yfinance",
    "get_ttm_analysis": "yfinance (derived)",
    "get_peer_comparison": "yfinance (derived)",
    "get_sector_relative": "yfinance (derived)",
    "get_macro_regime": "yfinance (derived)",
    # News
    "get_news": "yfinance",
    "get_global_news": "yfinance",
    "get_insider_transactions": "finnhub",
    # Scanner
    "get_market_movers": "yfinance",
    "get_market_indices": "finnhub",
    "get_sector_performance": "finnhub",
    "get_industry_performance": "yfinance",
    "get_topic_news": "finnhub",
    "get_earnings_calendar": "finnhub",
    "get_economic_calendar": "finnhub",
    # Finviz smart money
    "get_insider_buying_stocks": "finviz",
    "get_unusual_volume_stocks": "finviz",
    "get_breakout_accumulation_stocks": "finviz",
    # Portfolio (local)
    "get_enriched_holdings": "local",
    "compute_portfolio_risk_metrics": "local",
    "load_portfolio_risk_metrics": "local",
    "load_portfolio_decision": "local",
}


NODE_TO_PHASE = {
    # Phase analysts: re-run full pipeline from scratch
    "Market Analyst": "analysts",
    "Social Analyst": "analysts",
    "News Analyst": "analysts",
    "Fundamentals Analyst": "analysts",
    # Phase debate_and_trader: load analysts_checkpoint, skip analysts
    "Bull Researcher": "debate_and_trader",
    "Bear Researcher": "debate_and_trader",
    "Research Manager": "debate_and_trader",
    "Trader": "debate_and_trader",
    # Phase risk: load trader_checkpoint, skip analysts+debate+trader
    "Aggressive Analyst": "risk",
    "Conservative Analyst": "risk",
    "Neutral Analyst": "risk",
    "Portfolio Manager": "risk",
}


class LangGraphEngine:
    """Orchestrates LangGraph pipeline executions and streams events."""

    def __init__(self):
        self.config = DEFAULT_CONFIG.copy()
        self.active_runs: Dict[str, Dict[str, Any]] = {}
        # Track node start times per run so we can compute latency
        self._node_start_times: Dict[str, Dict[str, float]] = {}
        # Track the last prompt per node so we can attach it to result events
        self._node_prompts: Dict[str, Dict[str, str]] = {}
        # Track the human-readable identifier (ticker / "MARKET" / portfolio_id) per run
        self._run_identifiers: Dict[str, str] = {}
        # Track RunLogger instances per run for JSONL persistence
        self._run_loggers: Dict[str, RunLogger] = {}

    # ------------------------------------------------------------------
    # Run logger lifecycle
    # ------------------------------------------------------------------

    def _start_run_logger(self, run_id: str, flow_id: str | None = None) -> RunLogger:
        """Create and register a ``RunLogger`` for the given run."""
        uri = self.config.get("mongo_uri")
        db = self.config.get("mongo_db") or "tradingagents"
        rl = RunLogger(run_id=run_id, mongo_uri=uri, mongo_db=db, flow_id=flow_id)
        self._run_loggers[run_id] = rl
        set_run_logger(rl)
        return rl

    def _finish_run_logger(self, run_id: str, log_dir: Path) -> None:
        """Persist the run log to *log_dir*/run_log.jsonl and clean up."""
        rl = self._run_loggers.pop(run_id, None)
        if rl is None:
            return
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            rl.write_log(log_dir / "run_log.jsonl")
        except Exception:
            logger.exception("Failed to write run log for run=%s", run_id)
        finally:
            set_run_logger(None)

    # ------------------------------------------------------------------
    # Run helpers
    # ------------------------------------------------------------------

    async def run_scan(
        self, run_id: str, params: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Run the 3-phase macro scanner and stream events."""
        date = params.get("date", time.strftime("%Y-%m-%d"))

        flow_id = params.get("flow_id") or generate_flow_id()
        store = create_report_store(flow_id=flow_id)

        rl = self._start_run_logger(run_id, flow_id=flow_id)
        scan_config = {**self.config}
        if params.get("max_tickers"):
            scan_config["max_auto_tickers"] = int(params["max_tickers"])
        scanner = ScannerGraph(config=scan_config)

        logger.info("Starting SCAN run=%s date=%s flow_id=%s", run_id, date, flow_id)
        yield self._system_log(f"Starting macro scan for {date}")

        initial_state = {
            "scan_date": date,
            "messages": [],
            "geopolitical_report": "",
            "market_movers_report": "",
            "sector_performance_report": "",
            "industry_deep_dive_report": "",
            "macro_scan_summary": "",
            "sender": "",
        }

        self._node_start_times[run_id] = {}
        self._run_identifiers[run_id] = "MARKET"
        final_state: Dict[str, Any] = {}

        async for event in scanner.graph.astream_events(
            initial_state, version="v2", config={"callbacks": [rl.callback]}
        ):
            # Capture the complete final state from the root graph's terminal event.
            # LangGraph v2 emits one root-level on_chain_end (parent_ids=[], no
            # langgraph_node in metadata) whose data.output is the full accumulated state.
            if self._is_root_chain_end(event):
                output = (event.get("data") or {}).get("output")
                if isinstance(output, dict):
                    final_state = output
            mapped = self._map_langgraph_event(run_id, event)
            if mapped:
                yield mapped

        self._node_start_times.pop(run_id, None)
        self._node_prompts.pop(run_id, None)
        self._run_identifiers.pop(run_id, None)

        # Fallback: if the root on_chain_end event was never captured (can happen
        # with deeply nested sub-graphs), re-invoke to get the complete final state.
        if not final_state:
            logger.warning(
                "SCAN run=%s: root on_chain_end not captured — falling back to ainvoke",
                run_id,
            )
            try:
                final_state = await scanner.graph.ainvoke(initial_state)
            except Exception as exc:
                logger.warning("SCAN fallback ainvoke failed run=%s: %s", run_id, exc)

        # Save scan reports
        if final_state:
            yield self._system_log("Saving scan reports…")
            try:
                save_dir = get_market_dir(date, flow_id=flow_id)
                save_dir.mkdir(parents=True, exist_ok=True)

                for key in (
                    "geopolitical_report",
                    "market_movers_report",
                    "sector_performance_report",
                    "industry_deep_dive_report",
                    "macro_scan_summary",
                ):
                    content = final_state.get(key, "")
                    if content:
                        (save_dir / f"{key}.md").write_text(content)

                # Parse and save macro_scan_summary.json via store for downstream use
                summary_text = final_state.get("macro_scan_summary", "")
                if summary_text:
                    try:
                        summary_data = extract_json(summary_text)
                        store.save_scan(date, summary_data)
                    except (ValueError, KeyError, TypeError):
                        logger.warning(
                            "macro_scan_summary for date=%s is not valid JSON "
                            "(summary already saved as .md — downstream loads may fail)",
                            date,
                        )

                # Append to daily digest
                scan_parts = []
                for key, label in (
                    ("geopolitical_report", "Geopolitical & Macro"),
                    ("market_movers_report", "Market Movers"),
                    ("sector_performance_report", "Sector Performance"),
                    ("industry_deep_dive_report", "Industry Deep Dive"),
                    ("macro_scan_summary", "Macro Scan Summary"),
                ):
                    content = final_state.get(key, "")
                    if content:
                        scan_parts.append(f"### {label}\n{content}")
                if scan_parts:
                    append_to_digest(date, "scan", "Market Scan", "\n\n".join(scan_parts))

                yield self._system_log(f"Scan reports saved to {save_dir}")
                logger.info("Saved scan reports run=%s date=%s dir=%s", run_id, date, save_dir)
            except Exception as exc:
                logger.exception("Failed to save scan reports run=%s", run_id)
                yield self._system_log(f"Warning: could not save scan reports: {exc}")

        logger.info("Completed SCAN run=%s", run_id)
        self._finish_run_logger(run_id, get_market_dir(date, flow_id=flow_id))

    async def run_pipeline(
        self, run_id: str, params: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Run per-ticker analysis pipeline and stream events."""
        ticker = params.get("ticker", "AAPL")
        date = params.get("date", time.strftime("%Y-%m-%d"))
        analysts = params.get("analysts", ["market", "news", "fundamentals"])

        flow_id = params.get("flow_id") or generate_flow_id()
        store = create_report_store(flow_id=flow_id)

        rl = self._start_run_logger(run_id, flow_id=flow_id)

        logger.info("Starting PIPELINE run=%s ticker=%s date=%s flow_id=%s", run_id, ticker, date, flow_id)

        yield self._system_log(f"Starting analysis pipeline for {ticker} on {date}")

        graph_wrapper = TradingAgentsGraph(
            selected_analysts=analysts,
            config=self.config,
            debug=True,
        )

        initial_state = graph_wrapper.propagator.create_initial_state(ticker, date)

        self._node_start_times[run_id] = {}
        self._run_identifiers[run_id] = ticker.upper()
        final_state: Dict[str, Any] = {}

        try:
            async for event in graph_wrapper.graph.astream_events(
                initial_state,
                version="v2",
                config={
                    "recursion_limit": graph_wrapper.propagator.max_recur_limit,
                    "callbacks": [rl.callback],
                },
            ):
                # Capture the complete final state from the root graph's terminal event.
                if self._is_root_chain_end(event):
                    output = (event.get("data") or {}).get("output")
                    if isinstance(output, dict):
                        final_state = output
                mapped = self._map_langgraph_event(run_id, event)
                if mapped:
                    yield mapped
        except Exception as exc:
            if _is_policy_error(exc):
                model = self.config.get("quick_think_llm") or self.config.get("llm_provider", "unknown")
                provider = self.config.get("llm_provider", "unknown")
                raise RuntimeError(
                    f"LLM 404 (model={model}, provider={provider}): model blocked by "
                    f"provider policy — https://openrouter.ai/settings/privacy — "
                    f"or set TRADINGAGENTS_QUICK/MID/DEEP_THINK_FALLBACK_LLM."
                ) from exc
            raise

        self._node_start_times.pop(run_id, None)
        self._node_prompts.pop(run_id, None)
        self._run_identifiers.pop(run_id, None)

        # Fallback: if the root on_chain_end event was never captured (can happen
        # with deeply nested sub-graphs), re-invoke to get the complete final state.
        if not final_state:
            logger.warning(
                "PIPELINE run=%s ticker=%s: root on_chain_end not captured — "
                "falling back to ainvoke",
                run_id, ticker,
            )
            try:
                final_state = await graph_wrapper.graph.ainvoke(
                    initial_state,
                    config={"recursion_limit": graph_wrapper.propagator.max_recur_limit},
                )
            except Exception as exc:
                logger.warning("PIPELINE fallback ainvoke failed run=%s: %s", run_id, exc)

        # Save pipeline reports
        if final_state:
            yield self._system_log(f"Saving analysis report for {ticker}…")
            try:
                save_dir = get_ticker_dir(date, ticker, flow_id=flow_id)
                save_dir.mkdir(parents=True, exist_ok=True)

                # Sanitize final_state to remove non-JSON-serializable objects
                # (e.g. LangChain HumanMessage, AIMessage objects in "messages")
                serializable_state = self._sanitize_for_json(final_state)

                # Save JSON via store (complete_report.json)
                store.save_analysis(date, ticker, serializable_state)

                # Write human-readable complete_report.md
                self._write_complete_report_md(final_state, ticker, save_dir)

                # Append to daily digest
                digest_content = (
                    final_state.get("final_trade_decision")
                    or final_state.get("trader_investment_plan")
                    or ""
                )
                if digest_content:
                    append_to_digest(date, "analyze", ticker, digest_content)

                # Save analysts checkpoint (all 4 analyst reports populated)
                _analyst_keys = ("market_report", "sentiment_report", "news_report", "fundamentals_report")
                if all(final_state.get(k) for k in _analyst_keys):
                    analysts_ckpt = {
                        "company_of_interest": ticker,
                        "trade_date": date,
                        **{k: serializable_state.get(k, "") for k in _analyst_keys},
                        "macro_regime_report": serializable_state.get("macro_regime_report", ""),
                        "messages": serializable_state.get("messages", []),
                    }
                    store.save_analysts_checkpoint(date, ticker, analysts_ckpt)

                # Save trader checkpoint (trader output populated)
                if final_state.get("trader_investment_plan"):
                    trader_ckpt = {
                        "company_of_interest": ticker,
                        "trade_date": date,
                        **{k: serializable_state.get(k, "") for k in _analyst_keys},
                        "macro_regime_report": serializable_state.get("macro_regime_report", ""),
                        "investment_debate_state": serializable_state.get("investment_debate_state", {}),
                        "investment_plan": serializable_state.get("investment_plan", ""),
                        "trader_investment_plan": serializable_state.get("trader_investment_plan", ""),
                        "messages": serializable_state.get("messages", []),
                    }
                    store.save_trader_checkpoint(date, ticker, trader_ckpt)

                yield self._system_log(f"Analysis report for {ticker} saved to {save_dir}")
                logger.info("Saved pipeline report run=%s ticker=%s dir=%s", run_id, ticker, save_dir)
            except Exception as exc:
                logger.exception("Failed to save pipeline reports run=%s ticker=%s", run_id, ticker)
                yield self._system_log(f"Warning: could not save analysis report for {ticker}: {exc}")

        logger.info("Completed PIPELINE run=%s", run_id)
        self._finish_run_logger(run_id, get_ticker_dir(date, ticker, flow_id=flow_id))

    async def run_portfolio(
        self, run_id: str, params: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Run the portfolio manager workflow and stream events."""
        date = params.get("date", time.strftime("%Y-%m-%d"))
        portfolio_id = params.get("portfolio_id", "main_portfolio")

        flow_id = params.get("flow_id") or generate_flow_id()
        store = create_report_store(flow_id=flow_id)
        # A reader store with no flow_id resolves via latest pointer for loading
        reader_store = create_report_store()

        rl = self._start_run_logger(run_id, flow_id=flow_id)

        logger.info(
            "Starting PORTFOLIO run=%s portfolio=%s date=%s flow_id=%s",
            run_id, portfolio_id, date, flow_id,
        )
        yield self._system_log(
            f"Starting portfolio manager for {portfolio_id} on {date}"
        )

        portfolio_graph = PortfolioGraph(config=self.config)

        # Load scan summary and per-ticker analyses from the latest report
        scan_summary = reader_store.load_scan(date) or {}
        ticker_analyses: Dict[str, Any] = {}

        # Search both run-scoped and legacy flat layouts for ticker directories
        daily_dir = get_daily_dir(date)
        search_dirs: list[Path] = []
        runs_dir = daily_dir / "runs"
        if runs_dir.exists():
            for run_dir in runs_dir.iterdir():
                if run_dir.is_dir():
                    search_dirs.append(run_dir)
        if daily_dir.exists():
            search_dirs.append(daily_dir)

        seen_tickers: set[str] = set()
        for base in search_dirs:
            for ticker_dir in base.iterdir():
                if (
                    ticker_dir.is_dir()
                    and ticker_dir.name not in ("market", "portfolio", "runs")
                    and ticker_dir.name.upper() not in seen_tickers
                ):
                    analysis = reader_store.load_analysis(date, ticker_dir.name)
                    if analysis:
                        ticker_analyses[ticker_dir.name.upper()] = analysis
                        seen_tickers.add(ticker_dir.name.upper())

        if scan_summary:
            yield self._system_log(f"Loaded macro scan summary for {date}")
        else:
            yield self._system_log(f"No scan summary found for {date}, proceeding without it")
        if ticker_analyses:
            yield self._system_log(f"Loaded analyses for: {', '.join(sorted(ticker_analyses.keys()))}")
        else:
            yield self._system_log("No per-ticker analyses found for this date")

        # Merge ticker_analyses into scan_summary so portfolio graph nodes can access
        # per-ticker analysis data (PortfolioManagerState has no ticker_analyses field).
        if ticker_analyses:
            scan_summary["ticker_analyses"] = ticker_analyses

        # Collect tickers: current holdings + scan candidates, then fetch live prices
        holding_tickers: list[str] = []
        try:
            from tradingagents.portfolio.repository import PortfolioRepository
            _repo = PortfolioRepository()
            _, holdings = _repo.get_portfolio_with_holdings(portfolio_id)
            holding_tickers = [h.ticker for h in holdings]
        except Exception as exc:
            logger.warning("run_portfolio: could not load holdings for price fetch: %s", exc)
        candidate_tickers = [
            c if isinstance(c, str) else (c.get("ticker") or c.get("symbol") or "")
            for c in (scan_summary.get("stocks_to_investigate") or [])
        ]
        all_tickers = list({t.upper() for t in holding_tickers + candidate_tickers if t})
        prices = _fetch_prices(all_tickers) if all_tickers else {}

        initial_state = {
            "portfolio_id": portfolio_id,
            "analysis_date": date,        # PortfolioManagerState uses analysis_date
            "prices": prices,
            "scan_summary": scan_summary,
            "ticker_analyses": ticker_analyses,
            "messages": [],
            "portfolio_data": "",
            "risk_metrics": "",
            "holding_reviews": "",
            "prioritized_candidates": "",
            "pm_decision": "",
            "execution_result": "",
            "sender": "",
        }

        self._node_start_times[run_id] = {}
        self._run_identifiers[run_id] = portfolio_id
        final_state: Dict[str, Any] = {}

        async for event in portfolio_graph.graph.astream_events(
            initial_state, version="v2", config={"callbacks": [rl.callback]}
        ):
            if self._is_root_chain_end(event):
                output = (event.get("data") or {}).get("output")
                if isinstance(output, dict):
                    final_state = output
            mapped = self._map_langgraph_event(run_id, event)
            if mapped:
                yield mapped

        self._node_start_times.pop(run_id, None)
        self._node_prompts.pop(run_id, None)
        self._run_identifiers.pop(run_id, None)

        # Fallback: if the root on_chain_end event was never captured, re-invoke.
        if not final_state:
            logger.warning(
                "PORTFOLIO run=%s: root on_chain_end not captured — falling back to ainvoke",
                run_id,
            )
            try:
                final_state = await portfolio_graph.graph.ainvoke(initial_state)
            except Exception as exc:
                logger.warning("PORTFOLIO fallback ainvoke failed run=%s: %s", run_id, exc)

        # Save portfolio reports (Holding Reviews, Risk Metrics, PM Decision, Execution Result)
        if final_state:
            try:
                # 1. Holding Reviews — save the raw string via store
                holding_reviews_str = final_state.get("holding_reviews")
                if holding_reviews_str:
                    try:
                        reviews = json.loads(holding_reviews_str) if isinstance(holding_reviews_str, str) else holding_reviews_str
                        if isinstance(reviews, dict):
                            for ticker, review_data in reviews.items():
                                store.save_holding_review(date, ticker, review_data)
                        else:
                            logger.warning("Unexpected holding_reviews format run=%s: %s", run_id, type(reviews))
                    except Exception as exc:
                        logger.warning("Failed to save holding_reviews run=%s: %s", run_id, exc)

                # 2. Risk Metrics
                risk_metrics_str = final_state.get("risk_metrics")
                if risk_metrics_str:
                    try:
                        metrics = json.loads(risk_metrics_str) if isinstance(risk_metrics_str, str) else risk_metrics_str
                        store.save_risk_metrics(date, portfolio_id, metrics)
                    except Exception as exc:
                        logger.warning("Failed to save risk_metrics run=%s: %s", run_id, exc)

                # 3. PM Decision
                pm_decision_str = final_state.get("pm_decision")
                if pm_decision_str:
                    try:
                        decision = json.loads(pm_decision_str) if isinstance(pm_decision_str, str) else pm_decision_str
                        store.save_pm_decision(date, portfolio_id, decision)
                    except Exception as exc:
                        logger.warning("Failed to save pm_decision run=%s: %s", run_id, exc)

                # 4. Execution Result
                execution_result_str = final_state.get("execution_result")
                if execution_result_str:
                    try:
                        execution = json.loads(execution_result_str) if isinstance(execution_result_str, str) else execution_result_str
                        store.save_execution_result(date, portfolio_id, execution)
                    except Exception as exc:
                        logger.warning("Failed to save execution_result run=%s: %s", run_id, exc)

                yield self._system_log(f"Portfolio stage reports (decision & execution) saved for {portfolio_id} on {date}")
            except Exception as exc:
                logger.exception("Failed to save portfolio reports run=%s", run_id)
                yield self._system_log(f"Warning: could not save portfolio reports: {exc}")

        logger.info("Completed PORTFOLIO run=%s", run_id)
        self._finish_run_logger(run_id, get_daily_dir(date, flow_id=flow_id) / "portfolio")

    async def run_trade_execution(
        self, run_id: str, date: str, portfolio_id: str, decision: dict, prices: dict,
        store: ReportStore | None = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Manually execute a pre-computed PM decision (for resumability)."""
        logger.info("Starting TRADE_EXECUTION run=%s portfolio=%s date=%s", run_id, portfolio_id, date)
        yield self._system_log(f"Resuming trade execution for {portfolio_id} using saved decision…")

        from tradingagents.portfolio.trade_executor import TradeExecutor
        from tradingagents.portfolio.repository import PortfolioRepository

        if not prices:
            tickers = _tickers_from_decision(decision)
            if tickers:
                yield self._system_log(f"Fetching live prices for {tickers} from yfinance…")
                prices = _fetch_prices(tickers)
                logger.info("TRADE_EXECUTION run=%s: fetched prices for %s", run_id, list(prices.keys()))
            if not prices:
                logger.warning("TRADE_EXECUTION run=%s: no prices available — execution may produce incomplete results", run_id)
                yield self._system_log(f"Warning: no prices found for {portfolio_id} on {date} — trade execution may be incomplete.")

        _store = store or create_report_store()

        try:
            repo = PortfolioRepository()
            executor = TradeExecutor(repo=repo, config=self.config)

            # Execute decisions
            result = executor.execute_decisions(portfolio_id, decision, prices, date=date)

            # Save results using the shared store instance
            _store.save_execution_result(date, portfolio_id, result)

            yield self._system_log(f"Trade execution completed for {portfolio_id}. {result.get('summary', {})}")
            logger.info("Completed TRADE_EXECUTION run=%s", run_id)
        except Exception as exc:
            logger.exception("Trade execution failed run=%s", run_id)
            yield self._system_log(f"Error during trade execution: {exc}")
            raise

    async def run_pipeline_from_phase(
        self, run_id: str, params: Dict[str, Any], phase: str,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Re-run a single ticker's pipeline from a specific phase.

        Phases:
            analysts        - full re-run (delegates to run_pipeline)
            debate_and_trader - load analysts_checkpoint, run debate+trader+risk subgraph
            risk            - load trader_checkpoint, run risk subgraph only

        After the subgraph completes the ticker's reports and checkpoints are
        overwritten and the portfolio manager is re-run so that the PM
        decision reflects the updated ticker analysis.
        """
        ticker = params.get("ticker", params.get("identifier", "AAPL"))
        date = params.get("date", time.strftime("%Y-%m-%d"))
        portfolio_id = params.get("portfolio_id", "main_portfolio")

        store = create_report_store()
        flow_id = params.get("flow_id") or generate_flow_id()
        writer_store = create_report_store(flow_id=flow_id)

        if phase == "analysts":
            # Full re-run
            async for evt in self.run_pipeline(run_id, {"ticker": ticker, "date": date}):
                yield evt
        elif phase == "debate_and_trader":
            yield self._system_log(f"Loading analysts checkpoint for {ticker}...")
            ckpt = store.load_analysts_checkpoint(date, ticker)
            if not ckpt:
                yield self._system_log(f"No analysts checkpoint found for {ticker} — falling back to full re-run")
                async for evt in self.run_pipeline(run_id, {"ticker": ticker, "date": date}):
                    yield evt
            else:
                yield self._system_log(f"Running debate + trader + risk for {ticker} from checkpoint...")
                graph_wrapper = TradingAgentsGraph(config=self.config, debug=True)
                initial_state = graph_wrapper.propagator.create_initial_state(ticker, date)
                # Overlay checkpoint data onto initial state
                for k, v in ckpt.items():
                    if k in initial_state or k in ("market_report", "sentiment_report", "news_report", "fundamentals_report", "macro_regime_report"):
                        initial_state[k] = v

                rl = self._start_run_logger(run_id)
                self._node_start_times[run_id] = {}
                self._run_identifiers[run_id] = ticker.upper()
                final_state: Dict[str, Any] = {}

                async for event in graph_wrapper.debate_graph.astream_events(
                    initial_state, version="v2",
                    config={"recursion_limit": graph_wrapper.propagator.max_recur_limit, "callbacks": [rl.callback]},
                ):
                    if self._is_root_chain_end(event):
                        output = (event.get("data") or {}).get("output")
                        if isinstance(output, dict):
                            final_state = output
                    mapped = self._map_langgraph_event(run_id, event)
                    if mapped:
                        yield mapped

                self._node_start_times.pop(run_id, None)
                self._node_prompts.pop(run_id, None)
                self._run_identifiers.pop(run_id, None)

                if final_state:
                    serializable_state = self._sanitize_for_json(final_state)
                    writer_store.save_analysis(date, ticker, serializable_state)
                    # Overwrite checkpoints
                    _analyst_keys = ("market_report", "sentiment_report", "news_report", "fundamentals_report")
                    if final_state.get("trader_investment_plan"):
                        trader_ckpt = {
                            "company_of_interest": ticker,
                            "trade_date": date,
                            **{k: serializable_state.get(k, "") for k in _analyst_keys},
                            "macro_regime_report": serializable_state.get("macro_regime_report", ""),
                            "investment_debate_state": serializable_state.get("investment_debate_state", {}),
                            "investment_plan": serializable_state.get("investment_plan", ""),
                            "trader_investment_plan": serializable_state.get("trader_investment_plan", ""),
                            "messages": serializable_state.get("messages", []),
                        }
                        writer_store.save_trader_checkpoint(date, ticker, trader_ckpt)

                self._finish_run_logger(run_id, get_ticker_dir(date, ticker, flow_id=flow_id))
        elif phase == "risk":
            yield self._system_log(f"Loading trader checkpoint for {ticker}...")
            ckpt = store.load_trader_checkpoint(date, ticker)
            if not ckpt:
                yield self._system_log(f"No trader checkpoint found for {ticker} — falling back to full re-run")
                async for evt in self.run_pipeline(run_id, {"ticker": ticker, "date": date}):
                    yield evt
            else:
                yield self._system_log(f"Running risk phase for {ticker} from checkpoint...")
                graph_wrapper = TradingAgentsGraph(config=self.config, debug=True)
                initial_state = graph_wrapper.propagator.create_initial_state(ticker, date)
                for k, v in ckpt.items():
                    if k != "messages":
                        initial_state[k] = v

                rl = self._start_run_logger(run_id)
                self._node_start_times[run_id] = {}
                self._run_identifiers[run_id] = ticker.upper()
                final_state: Dict[str, Any] = {}

                async for event in graph_wrapper.risk_graph.astream_events(
                    initial_state, version="v2",
                    config={"recursion_limit": graph_wrapper.propagator.max_recur_limit, "callbacks": [rl.callback]},
                ):
                    if self._is_root_chain_end(event):
                        output = (event.get("data") or {}).get("output")
                        if isinstance(output, dict):
                            final_state = output
                    mapped = self._map_langgraph_event(run_id, event)
                    if mapped:
                        yield mapped

                self._node_start_times.pop(run_id, None)
                self._node_prompts.pop(run_id, None)
                self._run_identifiers.pop(run_id, None)

                if final_state:
                    serializable_state = self._sanitize_for_json(final_state)
                    writer_store.save_analysis(date, ticker, serializable_state)

                self._finish_run_logger(run_id, get_ticker_dir(date, ticker, flow_id=flow_id))
        else:
            yield self._system_log(f"Unknown phase '{phase}' — skipping")
            return

        # Cascade: re-run portfolio manager with updated data
        yield self._system_log(f"Cascading: re-running portfolio manager after {ticker} {phase} re-run...")
        async for evt in self.run_portfolio(
            f"{run_id}_cascade_pm", {"date": date, "portfolio_id": portfolio_id}
        ):
            yield evt

    async def run_auto(
        self, run_id: str, params: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Run the full auto pipeline: scan → pipeline → portfolio."""
        date = params.get("date", time.strftime("%Y-%m-%d"))
        force = params.get("force", False)
        flow_id = params.get("flow_id") or generate_flow_id()

        # Thread the flow_id into params so all sub-phases share the same flow.
        params = {**params, "flow_id": flow_id}

        # Reader store scoped to this flow for skip-if-exists checks.
        store = create_report_store(flow_id=flow_id)

        self._start_run_logger(run_id, flow_id=flow_id)  # auto-run's own logger; sub-phases create their own

        logger.info("Starting AUTO run=%s flow=%s date=%s force=%s", run_id, flow_id, date, force)
        yield self._system_log(f"Starting full auto workflow for {date} (force={force}, flow={flow_id})")

        # Phase 1: Market scan
        yield self._system_log("Phase 1/3: Running market scan…")
        if not force and store.load_scan(date):
            yield self._system_log(f"Phase 1: Macro scan for {date} already exists, skipping.")
        else:
            scan_params = {"date": date, "flow_id": flow_id}
            if params.get("max_tickers"):
                scan_params["max_tickers"] = params["max_tickers"]
            async for evt in self.run_scan(f"{run_id}_scan", scan_params):
                yield evt

        # Phase 2: Pipeline analysis — get tickers from scan report + portfolio holdings
        yield self._system_log("Phase 2/3: Loading stocks from scan report…")
        scan_data = store.load_scan(date)
        scan_tickers = self._extract_tickers_from_scan_data(scan_data)

        # Safety cap: truncate scan candidates to max_auto_tickers (portfolio holdings added after)
        max_t = int(params.get("max_tickers") or self.config.get("max_auto_tickers") or 10)
        scan_tickers = scan_tickers[:max_t]

        # Also include tickers from current portfolio holdings so the PM agent
        # has fresh analysis for existing positions (hold/sell/add decisions).
        portfolio_id = params.get("portfolio_id", "main_portfolio")
        holding_tickers: list[str] = []
        try:
            from tradingagents.portfolio.repository import PortfolioRepository
            _repo = PortfolioRepository()
            _, holdings = _repo.get_portfolio_with_holdings(portfolio_id)
            holding_tickers = [h.ticker.upper() for h in holdings]
        except Exception as exc:
            logger.warning("run_auto: could not load holdings for pipeline: %s", exc)

        # Merge & deduplicate (scan candidates first, then holdings-only tickers)
        seen: set[str] = set()
        tickers: list[str] = []
        for t in scan_tickers:
            up = t.upper()
            if up not in seen:
                seen.add(up)
                tickers.append(up)
        holdings_only: list[str] = []
        for t in holding_tickers:
            if t not in seen:
                seen.add(t)
                tickers.append(t)
                holdings_only.append(t)

        if scan_tickers:
            yield self._system_log(
                f"Phase 2/3: {len(scan_tickers)} ticker(s) from scan report"
            )
        if holdings_only:
            yield self._system_log(
                f"Phase 2/3: {len(holdings_only)} additional ticker(s) from portfolio holdings: "
                + ", ".join(holdings_only)
            )

        if not tickers:
            yield self._system_log(
                "Warning: no stocks found in scan summary and no portfolio holdings — "
                "ensure the scan completed successfully and produced a "
                "'stocks_to_investigate' list. Skipping pipeline phase."
            )
        else:
            max_concurrent = int(self.config.get("max_concurrent_pipelines", 2))
            yield self._system_log(
                f"Phase 2/3: Queuing {len(tickers)} ticker(s) "
                f"(max {max_concurrent} concurrent)…"
            )

            # Run all tickers concurrently, bounded by a semaphore.
            # Events from all pipelines are funnelled through a shared queue
            # so this async generator can yield them as they arrive.
            _sentinel = object()
            pipeline_queue: asyncio.Queue = asyncio.Queue()
            semaphore = asyncio.Semaphore(max_concurrent)

            async def _run_one_ticker(ticker: str) -> None:
                async with semaphore:
                    if not force and store.load_analysis(date, ticker):
                        await pipeline_queue.put(
                            self._system_log(
                                f"Phase 2: Analysis for {ticker} on {date} already exists, skipping."
                            )
                        )
                        return
                    await pipeline_queue.put(
                        self._system_log(f"Phase 2/3: Running analysis pipeline for {ticker}…")
                    )
                    try:
                        async for evt in self.run_pipeline(
                            f"{run_id}_pipeline_{ticker}",
                            {"ticker": ticker, "date": date, "flow_id": flow_id},
                        ):
                            await pipeline_queue.put(evt)
                    except Exception as exc:
                        if _is_policy_error(exc):
                            logger.error(
                                "Pipeline blocked ticker=%s run=%s: %s", ticker, run_id, exc
                            )
                            fallback_config = _build_fallback_config(self.config)
                            if fallback_config:
                                fallback_models = ", ".join(
                                    f"{t}={fallback_config.get(f'{t}_llm', 'same')}"
                                    for t in ("quick_think", "mid_think", "deep_think")
                                    if fallback_config.get(f"{t}_llm") != self.config.get(f"{t}_llm")
                                )
                                await pipeline_queue.put(
                                    self._system_log(
                                        f"Primary model blocked for {ticker} — retrying with "
                                        f"fallback: {fallback_models}…"
                                    )
                                )
                                original_config = self.config
                                self.config = fallback_config
                                try:
                                    async for evt in self.run_pipeline(
                                        f"{run_id}_fallback_{ticker}",
                                        {"ticker": ticker, "date": date, "flow_id": flow_id},
                                    ):
                                        await pipeline_queue.put(evt)
                                except Exception as fallback_exc:
                                    logger.error(
                                        "Fallback pipeline failed ticker=%s: %s",
                                        ticker, fallback_exc,
                                    )
                                    await pipeline_queue.put(
                                        self._system_log(
                                            f"Warning: pipeline for {ticker} failed "
                                            f"(fallback also failed): {fallback_exc}"
                                        )
                                    )
                                finally:
                                    self.config = original_config
                            else:
                                await pipeline_queue.put(
                                    self._system_log(
                                        f"Warning: pipeline for {ticker} blocked by LLM provider policy. "
                                        f"{exc} — "
                                        f"Set TRADINGAGENTS_QUICK_THINK_FALLBACK_LLM (and MID/DEEP) "
                                        f"to auto-retry with a different model."
                                    )
                                )
                        else:
                            logger.exception(
                                "Pipeline failed ticker=%s run=%s", ticker, run_id
                            )
                            await pipeline_queue.put(
                                self._system_log(
                                    f"Warning: pipeline for {ticker} failed: {exc}"
                                )
                            )

            async def _pipeline_producer() -> None:
                await asyncio.gather(*[_run_one_ticker(t) for t in tickers])
                await pipeline_queue.put(_sentinel)

            asyncio.create_task(_pipeline_producer())

            while True:
                item = await pipeline_queue.get()
                if item is _sentinel:
                    break
                yield item

        # Phase 3: Portfolio management
        yield self._system_log("Phase 3/3: Running portfolio manager…")
        portfolio_params = {k: v for k, v in params.items() if k != "ticker"}
        portfolio_params["flow_id"] = flow_id
        portfolio_id = params.get("portfolio_id", "main_portfolio")

        # Check if portfolio stage is fully complete (execution result exists)
        if not force and store.load_execution_result(date, portfolio_id):
            yield self._system_log(f"Phase 3: Portfolio execution for {portfolio_id} on {date} already exists, skipping.")
        else:
            # Check if we can resume from a saved decision
            saved_decision = store.load_pm_decision(date, portfolio_id)
            if not force and saved_decision:
                yield self._system_log(f"Phase 3: Found saved PM decision for {portfolio_id}, resuming trade execution…")
                # Fetch live prices for all tickers referenced in the decision
                prices = _fetch_prices(_tickers_from_decision(saved_decision))
                async for evt in self.run_trade_execution(
                    f"{run_id}_resume_trades", date, portfolio_id, saved_decision, prices,
                    store=store,
                ):
                    yield evt
            else:
                # Run full portfolio graph (Decision + Execution)
                async for evt in self.run_portfolio(
                    f"{run_id}_portfolio", {"date": date, **portfolio_params}
                ):
                    yield evt

        logger.info("Completed AUTO run=%s", run_id)
        self._finish_run_logger(run_id, get_daily_dir(date, run_id=flow_id[:8]))

    # ------------------------------------------------------------------
    # Report helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _sanitize_for_json(obj: Any) -> Any:
        """Recursively convert non-JSON-serializable objects to plain types.

        LangGraph final states may contain LangChain message objects
        (HumanMessage, AIMessage, etc.) in the ``messages`` field, as well as
        other non-serializable objects from third-party libraries.  All such
        objects are converted to strings as a last resort so ``json.dumps``
        never raises ``TypeError``.
        """
        if isinstance(obj, dict):
            return {k: LangGraphEngine._sanitize_for_json(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [LangGraphEngine._sanitize_for_json(v) for v in obj]
        # LangChain message objects: convert to a safe dict representation
        if hasattr(obj, "content") and hasattr(obj, "type"):
            return {
                "type": str(getattr(obj, "type", "unknown")),
                "content": str(getattr(obj, "content", "")),
            }
        # Native JSON-serializable scalar types — return as-is
        if isinstance(obj, (str, int, float, bool, type(None))):
            return obj
        # Anything else (custom objects, datetimes, etc.) — stringify
        return str(obj)

    @staticmethod
    def _write_complete_report_md(
        final_state: Dict[str, Any], ticker: str, save_dir: Path
    ) -> None:
        """Write a human-readable complete_report.md from the pipeline final state."""
        sections = []
        header = (
            f"# Trading Analysis Report: {ticker}\n\n"
            f"Generated: {_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        )

        analyst_parts = []
        for key, label in (
            ("market_report", "Market Analyst"),
            ("sentiment_report", "Social Analyst"),
            ("news_report", "News Analyst"),
            ("fundamentals_report", "Fundamentals Analyst"),
        ):
            if final_state.get(key):
                analyst_parts.append(f"### {label}\n{final_state[key]}")
        if analyst_parts:
            sections.append("## I. Analyst Team Reports\n\n" + "\n\n".join(analyst_parts))

        if final_state.get("investment_plan"):
            sections.append(f"## II. Research Team Decision\n\n{final_state['investment_plan']}")

        if final_state.get("trader_investment_plan"):
            sections.append(f"## III. Trading Team Plan\n\n{final_state['trader_investment_plan']}")

        if final_state.get("final_trade_decision"):
            sections.append(f"## IV. Final Decision\n\n{final_state['final_trade_decision']}")

        (save_dir / "complete_report.md").write_text(header + "\n\n".join(sections))

    @staticmethod
    def _extract_tickers_from_scan_data(scan_data: Dict[str, Any] | None) -> list[str]:
        """Extract ticker symbols from a ReportStore scan summary dict.

        Handles two shapes from the macro synthesis LLM output:
        * List of dicts: ``[{'ticker': 'AAPL', ...}, ...]``
        * List of strings: ``['AAPL', 'TSLA', ...]``

        Also checks both ``stocks_to_investigate`` and ``watchlist`` keys.
        Returns an uppercase, deduplicated list in original order.
        """
        if not scan_data:
            return []
        raw_stocks = (
            scan_data.get("stocks_to_investigate")
            or scan_data.get("watchlist")
            or []
        )
        seen: set[str] = set()
        tickers: list[str] = []
        for item in raw_stocks:
            if isinstance(item, dict):
                sym = item.get("ticker") or item.get("symbol") or ""
            elif isinstance(item, str):
                sym = item
            else:
                continue
            sym = sym.strip().upper()
            if sym and sym not in seen:
                seen.add(sym)
                tickers.append(sym)
        return tickers

    # ------------------------------------------------------------------
    # Event mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _is_root_chain_end(event: Dict[str, Any]) -> bool:
        """Return True for the root-graph terminal event in a LangGraph v2 stream.

        LangGraph v2 emits one ``on_chain_end`` event per node AND one for the
        root graph itself.  The root-graph event is distinguished by:

        * ``event["metadata"]`` has no ``langgraph_node`` key  (node events always do)
        * ``event["parent_ids"]`` is empty  (root has no parent run)

        Its ``data["output"]`` contains the **complete** final state — the
        canonical way to read the propagated state without re-running the graph.
        """
        if event.get("event") != "on_chain_end":
            return False
        metadata = event.get("metadata") or {}
        if metadata.get("langgraph_node"):
            return False  # This is a node event, not the root
        parent_ids = event.get("parent_ids")
        return parent_ids is not None and len(parent_ids) == 0

    @staticmethod
    def _extract_node_name(event: Dict[str, Any]) -> str:
        """Extract the LangGraph node name from event metadata or tags."""
        # Prefer metadata.langgraph_node (most reliable)
        metadata = event.get("metadata") or {}
        node = metadata.get("langgraph_node")
        if node:
            return node

        # Fallback: tags like "graph:node:<name>"
        for tag in event.get("tags", []):
            if tag.startswith("graph:node:"):
                return tag.split(":", 2)[-1]

        # Last resort: the event name itself
        return event.get("name", "unknown")

    @staticmethod
    def _extract_content(obj: object) -> str:
        """Safely extract text content from a LangChain message or plain object."""
        content = getattr(obj, "content", None)
        # Handle cases where .content might be a method instead of a property
        if content is not None and callable(content):
            content = None
        return str(content) if content is not None else str(obj)

    @staticmethod
    def _truncate(text: str, max_len: int = _MAX_CONTENT_LEN) -> str:
        if len(text) <= max_len:
            return text
        return text[:max_len] + "…"

    @staticmethod
    def _system_log(message: str) -> Dict[str, Any]:
        """Create a log-type event for informational messages."""
        return {
            "id": f"log_{time.time_ns()}",
            "node_id": "__system__",
            "type": "log",
            "agent": "SYSTEM",
            "message": message,
            "metrics": {},
        }

    @staticmethod
    def _first_message_content(messages: Any) -> str:
        """Extract content from the first message in a LangGraph messages payload.

        ``messages`` may be a flat list of message objects or a list-of-lists.
        Returns an empty string when extraction fails.
        """
        if not isinstance(messages, list) or not messages:
            return ""
        first_item = messages[0]
        # Handle list-of-lists (nested batches)
        if isinstance(first_item, list):
            if not first_item:
                return ""
            first_item = first_item[0]
        content = getattr(first_item, "content", None)
        return str(content) if content is not None else str(first_item)

    def _extract_all_messages_content(self, messages: Any) -> str:
        """Extract text from ALL messages in a LangGraph messages payload.

        Returns the concatenated content of every message so the user can
        inspect the full prompt that was sent to the LLM.

        Handles several structures observed across LangChain / LangGraph versions:
        - flat list of message objects  ``[SystemMessage, HumanMessage, ...]``
        - list-of-lists (batched)       ``[[SystemMessage, HumanMessage, ...]]``
        - list of plain dicts            ``[{'role': 'system', 'content': '...'}]``
        - tuple wrapper                  ``([SystemMessage, ...],)``
        """
        if not messages:
            return ""

        # Unwrap single-element tuple / list-of-lists
        items: list = messages if isinstance(messages, list) else list(messages)
        if items and isinstance(items[0], (list, tuple)):
            items = list(items[0])

        parts: list[str] = []
        for msg in items:
            # LangChain message objects have .content and .type
            content = getattr(msg, "content", None)
            role = getattr(msg, "type", None)
            # Plain-dict messages (e.g. {"role": "user", "content": "..."})
            if content is None and isinstance(msg, dict):
                content = msg.get("content", "")
                role = msg.get("role") or msg.get("type") or "unknown"
            if role is None:
                role = "unknown"
            text = str(content) if content is not None else str(msg)
            parts.append(f"[{role}] {text}")

        return "\n\n".join(parts)

    def _extract_model(self, event: Dict[str, Any]) -> str:
        """Best-effort extraction of the model name from a LangGraph event."""
        data = event.get("data") or {};

        # 1. invocation_params (standard LangChain)
        inv = data.get("invocation_params") or {}
        model = inv.get("model_name") or inv.get("model") or ""
        if model:
            return model

        # 2. Serialized kwargs (OpenRouter / ChatOpenAI)
        serialized = event.get("serialized") or data.get("serialized") or {}
        kwargs = serialized.get("kwargs") or {}
        model = kwargs.get("model_name") or kwargs.get("model") or ""
        if model:
            return model

        # 3. metadata.ls_model_name (LangSmith tracing)
        metadata = event.get("metadata") or {}
        model = metadata.get("ls_model_name") or ""
        if model:
            return model

        return "unknown"

    @staticmethod
    def _safe_dict(obj: object) -> Dict[str, Any]:
        """Return *obj* if it is a dict, otherwise an empty dict.

        Many LangChain message objects expose dict-like metadata
        properties (``usage_metadata``, ``response_metadata``) but some
        providers return non-dict types (e.g. bound methods, None, or
        custom objects).  This helper guarantees safe ``.get()`` calls.
        """
        return obj if isinstance(obj, dict) else {}

    def _map_langgraph_event(
        self, run_id: str, event: Dict[str, Any]
    ) -> Dict[str, Any] | None:
        """Map LangGraph v2 events to AgentOS frontend contract.

        Each branch is wrapped in a ``try / except`` so that a single
        unexpected object shape never crashes the whole streaming loop.
        """
        kind = event.get("event", "")
        name = event.get("name", "unknown")
        node_name = self._extract_node_name(event)

        starts = self._node_start_times.get(run_id, {})
        prompts = self._node_prompts.setdefault(run_id, {})
        identifier = self._run_identifiers.get(run_id, "")

        # ------ LLM start ------
        if kind == "on_chat_model_start":
            try:
                starts[node_name] = time.monotonic()

                data = event.get("data") or {}

                # Extract the full prompt being sent to the LLM.
                # Try multiple paths observed in different LangChain versions:
                #   1. data.messages  (most common)
                #   2. data.input.messages  (newer LangGraph)
                #   3. data.input  (if it's a list of messages itself)
                #   4. data.kwargs.messages  (some providers)
                full_prompt = ""
                for source in (
                    data.get("messages"),
                    (data.get("input") or {}).get("messages") if isinstance(data.get("input"), dict) else None,
                    data.get("input") if isinstance(data.get("input"), (list, tuple)) else None,
                    (data.get("kwargs") or {}).get("messages"),
                ):
                    if source:
                        full_prompt = self._extract_all_messages_content(source)
                        if full_prompt:
                            break

                # If all structured extractions failed, dump a raw preview
                if not full_prompt:
                    raw_dump = str(data)[:_MAX_FULL_LEN]
                    if raw_dump and raw_dump != "{}":
                        full_prompt = f"[raw event data] {raw_dump}"

                prompt_snippet = self._truncate(
                    full_prompt.replace("\n", " "), _MAX_CONTENT_LEN
                ) if full_prompt else ""

                # Remember the full prompt so we can attach it to the result event
                prompts[node_name] = full_prompt

                model = self._extract_model(event)

                logger.info(
                    "LLM start node=%s model=%s run=%s", node_name, model, run_id
                )

                return {
                    "id": event.get("run_id", f"thought_{time.time_ns()}").strip(),
                    "node_id": node_name,
                    "parent_node_id": "start",
                    "type": "thought",
                    "agent": node_name.upper(),
                    "identifier": identifier,
                    "message": f"Prompting {model}…"
                    + (f" | {prompt_snippet}" if prompt_snippet else ""),
                    "prompt": full_prompt,
                    "metrics": {"model": model},
                }
            except Exception:
                logger.exception("Error mapping on_chat_model_start run=%s", run_id)
                return {
                    "id": f"thought_err_{time.time_ns()}",
                    "node_id": node_name,
                    "type": "thought",
                    "agent": node_name.upper(),
                    "identifier": identifier,
                    "message": f"Prompting LLM… (event parse error)",
                    "prompt": "",
                    "metrics": {},
                }

        # ------ Tool call ------
        elif kind == "on_tool_start":
            try:
                full_input = ""
                tool_input = ""
                inp = (event.get("data") or {}).get("input")
                if inp:
                    full_input = str(inp)[:_MAX_FULL_LEN]
                    tool_input = self._truncate(str(inp))

                service = _TOOL_SERVICE_MAP.get(name, "")

                logger.info("Tool start tool=%s service=%s node=%s run=%s", name, service, node_name, run_id)

                return {
                    "id": event.get("run_id", f"tool_{time.time_ns()}").strip(),
                    "node_id": f"tool_{name}",
                    "parent_node_id": node_name,
                    "type": "tool",
                    "agent": node_name.upper(),
                    "identifier": identifier,
                    "message": f"▶ Tool: {name}"
                    + (f" | {tool_input}" if tool_input else ""),
                    "prompt": full_input,
                    "service": service,
                    "status": "running",
                    "metrics": {},
                }
            except Exception:
                logger.exception("Error mapping on_tool_start run=%s", run_id)
                return None

        # ------ Tool result ------
        elif kind == "on_tool_end":
            try:
                full_output = ""
                tool_output = ""
                is_error = False
                error_message = ""
                graceful = False
                out = (event.get("data") or {}).get("output")
                if out is not None:
                    raw = self._extract_content(out)
                    full_output = raw[:_MAX_FULL_LEN]
                    tool_output = self._truncate(raw)
                    # Detect errors in tool output
                    if raw.startswith("Error") or raw.startswith("Error calling "):
                        is_error = True
                        error_message = raw[:500]
                    # Detect graceful degradation (vendor fallback / empty-but-ok)
                    raw_lower = raw.lower()
                    if any(kw in raw_lower for kw in _GRACEFUL_SKIP_KEYWORDS):
                        graceful = True
                # Some LangGraph versions pass errors through the event status
                evt_status = (event.get("data") or {}).get("status")
                if evt_status == "error":
                    is_error = True
                    if not error_message:
                        error_message = tool_output or "Unknown tool error"

                service = _TOOL_SERVICE_MAP.get(name, "")
                status = "error" if is_error else ("graceful_skip" if graceful else "success")
                icon = "✗" if is_error else ("⚠" if graceful else "✓")

                logger.info(
                    "Tool end tool=%s status=%s node=%s run=%s",
                    name, status, node_name, run_id,
                )

                return {
                    "id": f"{event.get('run_id', 'tool_end')}_{time.time_ns()}",
                    "node_id": f"tool_{name}",
                    "parent_node_id": node_name,
                    "type": "tool_result",
                    "agent": node_name.upper(),
                    "identifier": identifier,
                    "message": f"{icon} Tool result: {name}"
                    + (f" | {tool_output}" if tool_output else ""),
                    "response": full_output,
                    "service": service,
                    "status": status,
                    "error": error_message if is_error else None,
                    "metrics": {},
                }
            except Exception:
                logger.exception("Error mapping on_tool_end run=%s", run_id)
                return None

        # ------ LLM end ------
        elif kind == "on_chat_model_end":
            try:
                output = (event.get("data") or {}).get("output")
                usage: Dict[str, Any] = {}
                model = "unknown"
                response_snippet = ""
                full_response = ""

                if output is not None:
                    # Safely extract usage & response metadata (must be dicts)
                    usage_raw = getattr(output, "usage_metadata", None)
                    usage = self._safe_dict(usage_raw)

                    resp_meta = getattr(output, "response_metadata", None)
                    resp_dict = self._safe_dict(resp_meta)
                    if resp_dict:
                        model = resp_dict.get("model_name") or resp_dict.get("model", model)

                    # Extract the response text – handle message objects and dicts
                    raw = self._extract_content(output)

                    # If .content was empty or the repr of the whole object, try harder
                    if not raw or raw.startswith("<") or raw == str(output):
                        # Some providers wrap in .text or .message
                        potential_text = getattr(output, "text", None)
                        if potential_text is None or callable(potential_text):
                            potential_text = ""
                        if not isinstance(potential_text, str):
                            potential_text = str(potential_text)

                        raw = (
                            potential_text
                            or (output.get("content", "") if isinstance(output, dict) else "")
                        )

                    # Ensure raw is always a string before slicing
                    if not isinstance(raw, str):
                        raw = str(raw) if raw is not None else ""

                    if raw:
                        full_response = raw[:_MAX_FULL_LEN]
                        response_snippet = self._truncate(raw)

                # Fall back to event-level model extraction
                if model == "unknown":
                    model = self._extract_model(event)

                latency_ms = 0
                start_t = starts.pop(node_name, None)
                if start_t is not None:
                    latency_ms = round((time.monotonic() - start_t) * 1000)

                # Retrieve the prompt that started this LLM call
                matched_prompt = prompts.pop(node_name, "")

                tokens_in = usage.get("input_tokens", 0)
                tokens_out = usage.get("output_tokens", 0)

                logger.info(
                    "LLM end node=%s model=%s tokens_in=%s tokens_out=%s latency=%dms run=%s",
                    node_name,
                    model,
                    tokens_in or "?",
                    tokens_out or "?",
                    latency_ms,
                    run_id,
                )

                return {
                    "id": f"{event.get('run_id', 'result')}_{time.time_ns()}",
                    "node_id": node_name,
                    "type": "result",
                    "agent": node_name.upper(),
                    "identifier": identifier,
                    "message": response_snippet or "Completed.",
                    "prompt": matched_prompt,
                    "response": full_response,
                    "metrics": {
                        "model": model,
                        "tokens_in": tokens_in if isinstance(tokens_in, (int, float)) else 0,
                        "tokens_out": tokens_out if isinstance(tokens_out, (int, float)) else 0,
                        "latency_ms": latency_ms,
                    },
                }
            except Exception:
                logger.exception("Error mapping on_chat_model_end run=%s", run_id)
                matched_prompt = prompts.pop(node_name, "")
                return {
                    "id": f"result_err_{time.time_ns()}",
                    "node_id": node_name,
                    "type": "result",
                    "agent": node_name.upper(),
                    "identifier": identifier,
                    "message": "Completed (event parse error).",
                    "prompt": matched_prompt,
                    "response": "",
                    "metrics": {"model": "unknown", "tokens_in": 0, "tokens_out": 0, "latency_ms": 0},
                }

        return None

    # ------------------------------------------------------------------
    # Background task wrappers
    # ------------------------------------------------------------------

    async def run_scan_background(self, run_id: str, params: Dict[str, Any]):
        async for _ in self.run_scan(run_id, params):
            pass

    async def run_pipeline_background(self, run_id: str, params: Dict[str, Any]):
        async for _ in self.run_pipeline(run_id, params):
            pass

    async def run_portfolio_background(self, run_id: str, params: Dict[str, Any]):
        async for _ in self.run_portfolio(run_id, params):
            pass

    async def run_auto_background(self, run_id: str, params: Dict[str, Any]):
        async for _ in self.run_auto(run_id, params):
            pass
