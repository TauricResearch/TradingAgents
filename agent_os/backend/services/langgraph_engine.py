import asyncio
import datetime as _dt
import json
import logging
import time
from pathlib import Path
from typing import Dict, Any, AsyncGenerator
from agent_os.backend.store import runs as live_runs
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.graph.scanner_graph import ScannerGraph
from tradingagents.graph.portfolio_graph import PortfolioGraph
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.report_paths import get_market_dir, get_ticker_dir, get_daily_dir
from tradingagents.portfolio.report_store import ReportStore
from tradingagents.portfolio.store_factory import create_report_store
from tradingagents.daily_digest import append_to_digest
from tradingagents.agents.utils.json_utils import extract_json
from tradingagents.instruments import (
    CanonicalInstrument,
    is_equity_pipeline_supported,
    resolve_instrument,
)
from tradingagents.agents.utils.scanner_tools import (
    get_gold_price,
    get_oil_prices,
    get_bitcoin_price,
    get_eur_usd_rate,
    get_jpy_usd_rate,
    get_cny_usd_rate,
    get_earnings_calendar,
    get_economic_calendar,
)
from tradingagents.observability import RunLogger, set_run_logger

logger = logging.getLogger("agent_os.engine")


class AwaitPhase3Decision(RuntimeError):
    """Raised when auto mode must pause for a user decision before Phase 3."""

    def __init__(self, payload: dict[str, Any]):
        self.payload = payload
        incomplete = payload.get("incomplete_tickers") or []
        summary = ", ".join(
            f"{item.get('ticker')} ({item.get('reason')})"
            for item in incomplete
            if isinstance(item, dict)
        ) or "unknown ticker state"
        super().__init__(f"Ticker analyses require a decision before Phase 3: {summary}")

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


def _is_rate_limit_error(exc: Exception) -> bool:
    """Return True if *exc* looks like a temporary upstream/provider rate limit."""
    if getattr(exc, "status_code", None) == 429:
        return True
    cause = getattr(exc, "__cause__", None)
    if getattr(cause, "status_code", None) == 429:
        return True
    msg = str(exc).lower()
    return any(
        token in msg
        for token in (
            "temporarily rate-limited upstream",
            "retry shortly",
            "rate limited upstream",
            "rate-limited upstream",
            "rate limit",
            "429",
        )
    )


def _is_fallback_eligible_error(exc: Exception) -> bool:
    """Return True if *exc* should trigger per-tier fallback LLM substitution."""
    return _is_policy_error(exc) or _is_rate_limit_error(exc)


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


def _fallback_model_summary(current_config: dict, fallback_config: dict) -> str:
    return ", ".join(
        f"{tier}={fallback_config.get(f'{tier}_llm', 'same')}"
        for tier in ("quick_think", "mid_think", "deep_think")
        if fallback_config.get(f"{tier}_llm") != current_config.get(f"{tier}_llm")
    )

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


def _analysis_status(analysis: Any) -> str:
    """Return the normalized analysis status for a saved ticker artifact."""
    if not isinstance(analysis, dict):
        return "missing"
    status = str(analysis.get("analysis_status") or "").strip().lower()
    has_final_decision = bool(str(analysis.get("final_trade_decision") or "").strip())
    if status == "aborted":
        return status
    if has_final_decision:
        return "completed"
    if status:
        return status
    return "incomplete"


def _analysis_is_completed(analysis: Any) -> bool:
    return _analysis_status(analysis) == "completed"


def _analysis_is_terminal(analysis: Any) -> bool:
    return _analysis_status(analysis) in {"completed", "aborted"}


def _analysis_has_deep_dive(analysis: Any) -> bool:
    """Return True when a ticker analysis contains a completed deep-dive output."""
    if not isinstance(analysis, dict):
        return False
    status = str(analysis.get("analysis_status") or "").strip().lower()
    if status == "aborted":
        return False
    if status == "completed":
        return True
    return bool(str(analysis.get("final_trade_decision") or "").strip())


def _run_should_stop(run_id: str) -> bool:
    """Return True when a graceful stop has been requested for the root run."""
    return bool((live_runs.get(run_id) or {}).get("stop_requested"))


def _normalize_analysis_status(analysis: dict[str, Any]) -> str:
    """Persist a terminal status whenever a final trade decision is present."""
    status = str(analysis.get("analysis_status") or "").strip().lower()
    if status == "aborted":
        return status
    if str(analysis.get("final_trade_decision") or "").strip():
        return "completed"
    if status:
        return status
    return "incomplete"

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

SCAN_NODE_TO_REPORT_FIELD = {
    "gatekeeper_scanner": "gatekeeper_universe_report",
    "geopolitical_scanner": "geopolitical_report",
    "market_movers_scanner": "market_movers_report",
    "sector_scanner": "sector_performance_report",
    "factor_alignment_scanner": "factor_alignment_report",
    "drift_scanner": "drift_opportunities_report",
    "smart_money_scanner": "smart_money_report",
    "industry_deep_dive": "industry_deep_dive_report",
    "macro_synthesis": "macro_scan_summary",
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

    def _start_run_logger(self, run_id: str, *, logger_key: str | None = None) -> RunLogger:
        """Create and register a ``RunLogger`` for the given canonical run id."""
        uri = self.config.get("mongo_uri")
        db = self.config.get("mongo_db") or "tradingagents"
        rl = RunLogger(run_id=run_id, mongo_uri=uri, mongo_db=db)
        self._run_loggers[logger_key or run_id] = rl
        set_run_logger(rl)
        return rl

    def _finish_run_logger(self, logger_key: str, log_dir: Path) -> None:
        """Persist the run log to *log_dir*/run_log.jsonl and clean up."""
        rl = self._run_loggers.pop(logger_key, None)
        if rl is None:
            return
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            rl.write_log(log_dir / "run_log.jsonl")
        except Exception:
            logger.exception("Failed to write run log for logger_key=%s", logger_key)
        finally:
            set_run_logger(None)

    @staticmethod
    def _root_run_id(run_id: str, params: Dict[str, Any]) -> str:
        return params.get("run_id") or run_id

    @staticmethod
    def _execution_key(run_id: str, params: Dict[str, Any]) -> str:
        return params.get("_execution_key") or run_id

    # ------------------------------------------------------------------
    # Run helpers
    # ------------------------------------------------------------------

    async def run_scan(
        self, run_id: str, params: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Run the 3-phase macro scanner and stream events."""
        date = params.get("date", time.strftime("%Y-%m-%d"))
        root_run_id = self._root_run_id(run_id, params)
        execution_key = self._execution_key(run_id, params)
        store = create_report_store(run_id=root_run_id)

        rl = self._start_run_logger(root_run_id, logger_key=execution_key)
        scan_config = {**self.config}
        if params.get("max_tickers"):
            scan_config["max_auto_tickers"] = int(params["max_tickers"])
        scanner = ScannerGraph(config=scan_config)

        logger.info("Starting SCAN run=%s date=%s", root_run_id, date)
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

        self._node_start_times[execution_key] = {}
        self._run_identifiers[execution_key] = "MARKET"
        final_state: Dict[str, Any] = {}
        captured_root_state = False

        try:
            async for event in scanner.graph.astream_events(
                initial_state, version="v2", config={"callbacks": [rl.callback]}
            ):
                if _run_should_stop(root_run_id):
                    logger.info("SCAN run=%s: graceful stop requested, aborting early", root_run_id)
                    yield self._system_log("Aborting macro scan due to graceful stop request.")
                    raise asyncio.CancelledError()

                # Capture the complete final state from the root graph's terminal event.
                # LangGraph v2 emits one root-level on_chain_end (parent_ids=[], no
                # langgraph_node in metadata) whose data.output is the full accumulated state.
                if self._is_root_chain_end(event):
                    output = (event.get("data") or {}).get("output")
                    if isinstance(output, dict):
                        captured_root_state = True
                        final_state = output
                mapped = self._map_langgraph_event(execution_key, event)
                if mapped:
                    yield mapped

            if not captured_root_state:
                message = (
                    f"Scan for {date} completed without a root final state; "
                    "refusing to re-run the graph because that can duplicate expensive work."
                )
                logger.error("SCAN run=%s: %s", root_run_id, message)
                yield self._system_log(f"Error: {message}")
                raise RuntimeError(message)

            if final_state:
                async for evt in self._save_scan_outputs(final_state, date, root_run_id, store):
                    yield evt

            logger.info("Completed SCAN run=%s", root_run_id)
        finally:
            self._node_start_times.pop(execution_key, None)
            self._node_prompts.pop(execution_key, None)
            self._run_identifiers.pop(execution_key, None)
            self._finish_run_logger(execution_key, get_market_dir(date, root_run_id))

    async def _save_scan_outputs(
        self,
        final_state: Dict[str, Any],
        date: str,
        root_run_id: str,
        store,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Persist scan artifacts and emit system log events."""
        yield self._system_log("Saving scan reports…")
        try:
            save_dir = get_market_dir(date, root_run_id)
            save_dir.mkdir(parents=True, exist_ok=True)

            for key in SCAN_NODE_TO_REPORT_FIELD.values():
                content = final_state.get(key, "")
                if content:
                    (save_dir / f"{key}.md").write_text(content)

            summary_text = final_state.get("macro_scan_summary", "")
            if summary_text:
                try:
                    summary_data = self._normalize_scan_summary(extract_json(summary_text))
                    store.save_scan(date, summary_data)
                except (ValueError, KeyError, TypeError):
                    logger.warning(
                        "macro_scan_summary for date=%s is not valid JSON "
                        "(summary already saved as .md — downstream loads may fail)",
                        date,
                    )

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
            logger.info("Saved scan reports run=%s date=%s dir=%s", root_run_id, date, save_dir)
        except Exception as exc:
            logger.exception("Failed to save scan reports run=%s", root_run_id)
            yield self._system_log(f"Warning: could not save scan reports: {exc}")

    async def run_scan_from_node(
        self,
        run_id: str,
        params: Dict[str, Any],
        start_node: str,
        initial_state: Dict[str, Any],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Continue a market scan from *start_node* using a seeded state."""
        if start_node not in SCAN_NODE_TO_REPORT_FIELD:
            yield self._system_log(f"Unknown scan node '{start_node}' — skipping")
            return

        date = params.get("date", time.strftime("%Y-%m-%d"))
        root_run_id = self._root_run_id(run_id, params)
        execution_key = self._execution_key(run_id, params)
        store = create_report_store(run_id=root_run_id)

        rl = self._start_run_logger(root_run_id, logger_key=execution_key)
        scan_config = {**self.config}
        if params.get("max_tickers"):
            scan_config["max_auto_tickers"] = int(params["max_tickers"])
        scanner = ScannerGraph(config=scan_config)
        graph = scanner.graph_from(start_node)

        logger.info("Starting SCAN rerun run=%s node=%s date=%s", root_run_id, start_node, date)
        yield self._system_log(f"Continuing macro scan from {start_node} for {date}")

        seeded_state = {
            "scan_date": date,
            "messages": [],
            "gatekeeper_universe_report": "",
            "geopolitical_report": "",
            "market_movers_report": "",
            "sector_performance_report": "",
            "factor_alignment_report": "",
            "drift_opportunities_report": "",
            "smart_money_report": "",
            "industry_deep_dive_report": "",
            "macro_scan_summary": "",
            "sender": "",
            **initial_state,
        }

        self._node_start_times[execution_key] = {}
        self._run_identifiers[execution_key] = "MARKET"
        final_state: Dict[str, Any] = {}
        captured_root_state = False

        try:
            async for event in graph.astream_events(
                seeded_state, version="v2", config={"callbacks": [rl.callback]}
            ):
                if self._is_root_chain_end(event):
                    output = (event.get("data") or {}).get("output")
                    if isinstance(output, dict):
                        captured_root_state = True
                        final_state = output
                mapped = self._map_langgraph_event(execution_key, event)
                if mapped:
                    yield mapped

            if not captured_root_state:
                message = f"Scan continuation from {start_node} for {date} completed without a root final state."
                logger.error("SCAN rerun run=%s: %s", root_run_id, message)
                yield self._system_log(f"Error: {message}")
                raise RuntimeError(message)

            if final_state:
                async for evt in self._save_scan_outputs(final_state, date, root_run_id, store):
                    yield evt

            logger.info("Completed SCAN rerun run=%s node=%s", root_run_id, start_node)
        finally:
            self._node_start_times.pop(execution_key, None)
            self._node_prompts.pop(execution_key, None)
            self._run_identifiers.pop(execution_key, None)
            self._finish_run_logger(execution_key, get_market_dir(date, root_run_id))

    async def run_pipeline(
        self, run_id: str, params: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Run per-ticker analysis pipeline and stream events."""
        instrument = resolve_instrument(params.get("ticker", "AAPL"), source_context="pipeline")
        ticker = instrument.canonical_symbol or "AAPL"
        date = params.get("date", time.strftime("%Y-%m-%d"))
        analysts = params.get("analysts", ["market", "news", "fundamentals"])
        root_run_id = self._root_run_id(run_id, params)
        execution_key = self._execution_key(run_id, params)
        store = create_report_store(run_id=root_run_id)

        rl = self._start_run_logger(root_run_id, logger_key=execution_key)

        logger.info("Starting PIPELINE run=%s ticker=%s date=%s", root_run_id, ticker, date)

        if not is_equity_pipeline_supported(instrument):
            yield self._system_log(
                f"Skipping stock deep-dive for {ticker}: "
                f"classified as {instrument.instrument_type} ({instrument.asset_class})."
            )
            logger.info(
                "Skipping unsupported pipeline instrument run=%s ticker=%s type=%s",
                root_run_id, ticker, instrument.instrument_type,
            )
            self._finish_run_logger(execution_key, get_ticker_dir(date, ticker, root_run_id))
            return

        yield self._system_log(f"Starting analysis pipeline for {ticker} on {date}")

        graph_wrapper = TradingAgentsGraph(
            selected_analysts=analysts,
            config=self.config,
            debug=True,
        )

        initial_state = graph_wrapper.propagator.create_initial_state(
            ticker,
            date,
            run_id=root_run_id,
            portfolio_context=params.get("portfolio_context", "candidate"),
            scanner_context_packet=params.get("scanner_context_packet", ""),
        )

        self._node_start_times[execution_key] = {}
        self._run_identifiers[execution_key] = ticker.upper()
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
                if _run_should_stop(root_run_id):
                    logger.info("PIPELINE run=%s ticker=%s: graceful stop requested, aborting early", root_run_id, ticker)
                    yield self._system_log(f"Aborting analysis for {ticker} due to graceful stop request.")
                    raise asyncio.CancelledError()

                # Capture the complete final state from the root graph's terminal event.
                if self._is_root_chain_end(event):
                    output = (event.get("data") or {}).get("output")
                    if isinstance(output, dict):
                        final_state = output
                mapped = self._map_langgraph_event(execution_key, event)
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

        self._node_start_times.pop(execution_key, None)
        self._node_prompts.pop(execution_key, None)
        self._run_identifiers.pop(execution_key, None)

        # Fallback: if the root on_chain_end event was never captured (can happen
        # with deeply nested sub-graphs), re-invoke to get the complete final state.
        if not final_state:
            logger.warning(
                "PIPELINE run=%s ticker=%s: root on_chain_end not captured — "
                "falling back to ainvoke",
                root_run_id, ticker,
            )
            try:
                final_state = await graph_wrapper.graph.ainvoke(
                    initial_state,
                    config={"recursion_limit": graph_wrapper.propagator.max_recur_limit},
                )
            except Exception as exc:
                logger.warning("PIPELINE fallback ainvoke failed run=%s: %s", root_run_id, exc)

        # Save pipeline reports
        if final_state:
            yield self._system_log(f"Saving analysis report for {ticker}…")
            try:
                save_dir = get_ticker_dir(date, ticker, root_run_id)
                save_dir.mkdir(parents=True, exist_ok=True)

                # Sanitize final_state to remove non-JSON-serializable objects
                # (e.g. LangChain HumanMessage, AIMessage objects in "messages")
                serializable_state = self._sanitize_for_json(final_state)
                serializable_state.update(instrument.to_metadata())
                serializable_state["ticker"] = ticker
                serializable_state["analysis_status"] = _normalize_analysis_status(serializable_state)

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

                # Save analysts checkpoint (any analyst report populated — social is optional)
                _analyst_keys = ("market_report", "sentiment_report", "news_report", "fundamentals_report")
                if any(final_state.get(k) for k in _analyst_keys):
                    analysts_ckpt = {
                        "company_of_interest": ticker,
                        "trade_date": date,
                        **{k: serializable_state.get(k, "") for k in _analyst_keys},
                        "macro_regime_report": serializable_state.get("macro_regime_report", ""),
                        "portfolio_context": serializable_state.get("portfolio_context", "candidate"),
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
                        "portfolio_context": serializable_state.get("portfolio_context", "candidate"),
                        "investment_debate_state": serializable_state.get("investment_debate_state", {}),
                        "investment_plan": serializable_state.get("investment_plan", ""),
                        "trader_investment_plan": serializable_state.get("trader_investment_plan", ""),
                        "messages": serializable_state.get("messages", []),
                    }
                    store.save_trader_checkpoint(date, ticker, trader_ckpt)

                yield self._system_log(f"Analysis report for {ticker} saved to {save_dir}")
                logger.info("Saved pipeline report run=%s ticker=%s dir=%s", root_run_id, ticker, save_dir)
            except Exception as exc:
                logger.exception("Failed to save pipeline reports run=%s ticker=%s", root_run_id, ticker)
                yield self._system_log(f"Warning: could not save analysis report for {ticker}: {exc}")

        logger.info("Completed PIPELINE run=%s", root_run_id)
        self._finish_run_logger(execution_key, get_ticker_dir(date, ticker, root_run_id))

    async def run_portfolio(
        self, run_id: str, params: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Run the portfolio manager workflow and stream events."""
        date = params.get("date", time.strftime("%Y-%m-%d"))
        portfolio_id = params.get("portfolio_id", "main_portfolio")
        root_run_id = self._root_run_id(run_id, params)
        execution_key = self._execution_key(run_id, params)
        store = create_report_store(run_id=root_run_id)
        reader_store = create_report_store(run_id=root_run_id)
        fallback_reader_store = create_report_store()

        rl = self._start_run_logger(root_run_id, logger_key=execution_key)

        logger.info(
            "Starting PORTFOLIO run=%s portfolio=%s date=%s",
            root_run_id, portfolio_id, date,
        )
        yield self._system_log(
            f"Starting portfolio manager for {portfolio_id} on {date}"
        )

        portfolio_graph = PortfolioGraph(config=self.config)

        scan_summary = self._normalize_scan_summary(
            reader_store.load_scan(date) or fallback_reader_store.load_scan(date) or {}
        )
        ticker_analyses: Dict[str, Any] = {}

        search_dirs: list[Path] = []
        run_daily_dir = get_daily_dir(date, root_run_id)
        all_daily_dir = get_daily_dir(date)
        if run_daily_dir.exists():
            search_dirs.append(run_daily_dir)
        elif all_daily_dir.exists():
            search_dirs.extend(sorted((p for p in all_daily_dir.iterdir() if p.is_dir()), reverse=True))

        seen_tickers: set[str] = set()
        incomplete_tickers: list[str] = []
        for base in search_dirs:
            for ticker_dir in base.iterdir():
                if (
                    ticker_dir.is_dir()
                    and ticker_dir.name not in ("market", "portfolio", "report")
                    and ticker_dir.name.upper() not in seen_tickers
                ):
                    analysis = reader_store.load_analysis(date, ticker_dir.name)
                    if analysis is None:
                        analysis = fallback_reader_store.load_analysis(date, ticker_dir.name)
                    instrument_key = (
                        (analysis or {}).get("instrument_key")
                        or resolve_instrument(ticker_dir.name, source_context="analysis").instrument_key
                    )
                    if _analysis_has_deep_dive(analysis):
                        ticker_analyses[instrument_key] = analysis
                        seen_tickers.add(instrument_key)
                    elif analysis:
                        incomplete_tickers.append(instrument_key)

        if scan_summary:
            yield self._system_log(f"Loaded macro scan summary for {date}")
        else:
            yield self._system_log(f"No scan summary found for {date}, proceeding without it")
        if ticker_analyses:
            yield self._system_log(f"Loaded analyses for: {', '.join(sorted(ticker_analyses.keys()))}")
        else:
            yield self._system_log("No per-ticker analyses found for this date")
        if incomplete_tickers:
            yield self._system_log(
                "Ignoring incomplete ticker analyses without deep-dive decisions: "
                + ", ".join(sorted(set(incomplete_tickers)))
            )

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
        analysis_tickers = [
            str(analysis.get("canonical_symbol") or analysis.get("ticker") or "").upper()
            for analysis in ticker_analyses.values()
        ]
        # Always include the cash-sweep ETF so the trade executor can price it
        CASH_SWEEP_ETF = "SGOV"
        all_tickers = list(
            {t.upper() for t in holding_tickers + analysis_tickers if t} | {CASH_SWEEP_ETF}
        )
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

        self._node_start_times[execution_key] = {}
        self._run_identifiers[execution_key] = portfolio_id
        final_state: Dict[str, Any] = {}

        async for event in portfolio_graph.graph.astream_events(
            initial_state, version="v2", config={"callbacks": [rl.callback]}
        ):
            if _run_should_stop(root_run_id):
                logger.info("PORTFOLIO run=%s: graceful stop requested, aborting early", root_run_id)
                yield self._system_log("Aborting portfolio management due to graceful stop request.")
                raise asyncio.CancelledError()

            if self._is_root_chain_end(event):
                output = (event.get("data") or {}).get("output")
                if isinstance(output, dict):
                    final_state = output
            mapped = self._map_langgraph_event(execution_key, event)
            if mapped:
                yield mapped

        self._node_start_times.pop(execution_key, None)
        self._node_prompts.pop(execution_key, None)
        self._run_identifiers.pop(execution_key, None)

        # Fallback: if the root on_chain_end event was never captured, re-invoke.
        if not final_state:
            logger.warning(
                "PORTFOLIO run=%s: root on_chain_end not captured — falling back to ainvoke",
                root_run_id,
            )
            try:
                final_state = await portfolio_graph.graph.ainvoke(initial_state)
            except Exception as exc:
                logger.warning("PORTFOLIO fallback ainvoke failed run=%s: %s", root_run_id, exc)

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
                            logger.warning("Unexpected holding_reviews format run=%s: %s", root_run_id, type(reviews))
                    except Exception as exc:
                        logger.warning("Failed to save holding_reviews run=%s: %s", root_run_id, exc)

                # 2. Risk Metrics
                risk_metrics_str = final_state.get("risk_metrics")
                if risk_metrics_str:
                    try:
                        metrics = json.loads(risk_metrics_str) if isinstance(risk_metrics_str, str) else risk_metrics_str
                        store.save_risk_metrics(date, portfolio_id, metrics)
                    except Exception as exc:
                        logger.warning("Failed to save risk_metrics run=%s: %s", root_run_id, exc)

                # 3. PM Decision
                pm_decision_str = final_state.get("pm_decision")
                if pm_decision_str:
                    try:
                        decision = json.loads(pm_decision_str) if isinstance(pm_decision_str, str) else pm_decision_str
                        store.save_pm_decision(date, portfolio_id, decision)
                    except Exception as exc:
                        logger.warning("Failed to save pm_decision run=%s: %s", root_run_id, exc)

                # 4. Execution Result
                execution_result_str = final_state.get("execution_result")
                if execution_result_str:
                    try:
                        execution = json.loads(execution_result_str) if isinstance(execution_result_str, str) else execution_result_str
                        store.save_execution_result(date, portfolio_id, execution)
                    except Exception as exc:
                        logger.warning("Failed to save execution_result run=%s: %s", root_run_id, exc)

                yield self._system_log(f"Portfolio stage reports (decision & execution) saved for {portfolio_id} on {date}")
            except Exception as exc:
                logger.exception("Failed to save portfolio reports run=%s", root_run_id)
                yield self._system_log(f"Warning: could not save portfolio reports: {exc}")

        logger.info("Completed PORTFOLIO run=%s", root_run_id)
        self._finish_run_logger(execution_key, get_daily_dir(date, root_run_id) / "portfolio")

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

        _store = store or create_report_store(run_id=run_id)

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
        instrument = resolve_instrument(ticker, source_context="pipeline_rerun")
        date = params.get("date", time.strftime("%Y-%m-%d"))
        portfolio_id = params.get("portfolio_id", "main_portfolio")
        root_run_id = self._root_run_id(run_id, params)
        execution_key = self._execution_key(run_id, params)
        store = create_report_store(run_id=root_run_id)
        fallback_store = create_report_store()
        writer_store = create_report_store(run_id=root_run_id)

        if not is_equity_pipeline_supported(instrument):
            yield self._system_log(
                f"Skipping {phase} re-run for {ticker}: "
                f"classified as {instrument.instrument_type} ({instrument.asset_class})."
            )
            return

        if phase == "analysts":
            # Full re-run
            async for evt in self.run_pipeline(execution_key, {"ticker": ticker, "date": date, "run_id": root_run_id, "portfolio_context": params.get("portfolio_context", "candidate"), "_execution_key": execution_key}):
                yield evt
        elif phase == "debate_and_trader":
            yield self._system_log(f"Loading analysts checkpoint for {ticker}...")
            ckpt = store.load_analysts_checkpoint(date, ticker) or fallback_store.load_analysts_checkpoint(date, ticker)
            if not ckpt:
                yield self._system_log(f"No analysts checkpoint found for {ticker} — falling back to full re-run")
                async for evt in self.run_pipeline(execution_key, {"ticker": ticker, "date": date, "run_id": root_run_id, "portfolio_context": params.get("portfolio_context", "candidate"), "_execution_key": execution_key}):
                    yield evt
            else:
                yield self._system_log(f"Running debate + trader + risk for {ticker} from checkpoint...")
                graph_wrapper = TradingAgentsGraph(config=self.config, debug=True)
                initial_state = graph_wrapper.propagator.create_initial_state(
                    ticker,
                    date,
                    run_id=root_run_id,
                    portfolio_context=ckpt.get("portfolio_context", "candidate"),
                )
                # Overlay checkpoint data onto initial state
                for k, v in ckpt.items():
                    if k in initial_state or k in ("market_report", "sentiment_report", "news_report", "fundamentals_report", "macro_regime_report"):
                        initial_state[k] = v

                rl = self._start_run_logger(root_run_id, logger_key=execution_key)
                self._node_start_times[execution_key] = {}
                self._run_identifiers[execution_key] = ticker.upper()
                final_state: Dict[str, Any] = {}

                async for event in graph_wrapper.debate_graph.astream_events(
                    initial_state, version="v2",
                    config={"recursion_limit": graph_wrapper.propagator.max_recur_limit, "callbacks": [rl.callback]},
                ):
                    if _run_should_stop(root_run_id):
                        logger.info("PIPELINE_RERUN run=%s ticker=%s: graceful stop requested, aborting early", root_run_id, ticker)
                        yield self._system_log(f"Aborting rerun for {ticker} due to graceful stop request.")
                        raise asyncio.CancelledError()

                    if self._is_root_chain_end(event):
                        output = (event.get("data") or {}).get("output")
                        if isinstance(output, dict):
                            final_state = output
                    mapped = self._map_langgraph_event(execution_key, event)
                    if mapped:
                        yield mapped

                self._node_start_times.pop(execution_key, None)
                self._node_prompts.pop(execution_key, None)
                self._run_identifiers.pop(execution_key, None)

                if final_state:
                    serializable_state = self._sanitize_for_json(final_state)
                    serializable_state["analysis_status"] = _normalize_analysis_status(serializable_state)
                    writer_store.save_analysis(date, ticker, serializable_state)
                    # Overwrite checkpoints
                    _analyst_keys = ("market_report", "sentiment_report", "news_report", "fundamentals_report")
                    if final_state.get("trader_investment_plan"):
                        trader_ckpt = {
                            "company_of_interest": ticker,
                            "trade_date": date,
                            **{k: serializable_state.get(k, "") for k in _analyst_keys},
                            "macro_regime_report": serializable_state.get("macro_regime_report", ""),
                            "portfolio_context": serializable_state.get("portfolio_context", "candidate"),
                            "investment_debate_state": serializable_state.get("investment_debate_state", {}),
                            "investment_plan": serializable_state.get("investment_plan", ""),
                            "trader_investment_plan": serializable_state.get("trader_investment_plan", ""),
                            "messages": serializable_state.get("messages", []),
                        }
                        writer_store.save_trader_checkpoint(date, ticker, trader_ckpt)

                self._finish_run_logger(execution_key, get_ticker_dir(date, ticker, root_run_id))
        elif phase == "risk":
            yield self._system_log(f"Loading trader checkpoint for {ticker}...")
            ckpt = store.load_trader_checkpoint(date, ticker) or fallback_store.load_trader_checkpoint(date, ticker)
            if not ckpt:
                yield self._system_log(f"No trader checkpoint found for {ticker} — falling back to full re-run")
                async for evt in self.run_pipeline(execution_key, {"ticker": ticker, "date": date, "run_id": root_run_id, "portfolio_context": params.get("portfolio_context", "candidate"), "_execution_key": execution_key}):
                    yield evt
            else:
                yield self._system_log(f"Running risk phase for {ticker} from checkpoint...")
                graph_wrapper = TradingAgentsGraph(config=self.config, debug=True)
                initial_state = graph_wrapper.propagator.create_initial_state(
                    ticker,
                    date,
                    run_id=root_run_id,
                    portfolio_context=ckpt.get("portfolio_context", "candidate"),
                )
                if not ckpt.get("investment_plan"):
                    raise ValueError(
                        f"Trader checkpoint for {ticker} on {date} is invalid: "
                        "missing required 'investment_plan'"
                    )
                for k, v in ckpt.items():
                    if k != "messages":
                        initial_state[k] = v

                rl = self._start_run_logger(root_run_id, logger_key=execution_key)
                self._node_start_times[execution_key] = {}
                self._run_identifiers[execution_key] = ticker.upper()
                final_state: Dict[str, Any] = {}

                async for event in graph_wrapper.risk_graph.astream_events(
                    initial_state, version="v2",
                    config={"recursion_limit": graph_wrapper.propagator.max_recur_limit, "callbacks": [rl.callback]},
                ):
                    if _run_should_stop(root_run_id):
                        logger.info("PIPELINE_RERUN_RISK run=%s ticker=%s: graceful stop requested, aborting early", root_run_id, ticker)
                        yield self._system_log(f"Aborting risk rerun for {ticker} due to graceful stop request.")
                        raise asyncio.CancelledError()

                    if self._is_root_chain_end(event):
                        output = (event.get("data") or {}).get("output")
                        if isinstance(output, dict):
                            final_state = output
                    mapped = self._map_langgraph_event(execution_key, event)
                    if mapped:
                        yield mapped

                self._node_start_times.pop(execution_key, None)
                self._node_prompts.pop(execution_key, None)
                self._run_identifiers.pop(execution_key, None)

                if final_state:
                    serializable_state = self._sanitize_for_json(final_state)
                    serializable_state["analysis_status"] = _normalize_analysis_status(serializable_state)
                    writer_store.save_analysis(date, ticker, serializable_state)

                self._finish_run_logger(execution_key, get_ticker_dir(date, ticker, root_run_id))
        else:
            yield self._system_log(f"Unknown phase '{phase}' — skipping")
            return

        # Cascade: re-run portfolio manager with updated data
        yield self._system_log(f"Cascading: re-running portfolio manager after {ticker} {phase} re-run...")
        async for evt in self.run_portfolio(
            f"{root_run_id}:cascade_pm:{ticker}:{phase}",
            {"date": date, "portfolio_id": portfolio_id, "run_id": root_run_id, "_execution_key": f"{root_run_id}:cascade_pm:{ticker}:{phase}"},
        ):
            yield evt

    async def run_auto(
        self, run_id: str, params: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Run the full auto pipeline: scan → pipeline → portfolio."""
        date = params.get("date", time.strftime("%Y-%m-%d"))
        force = params.get("force", False)
        continue_on_ticker_failure = bool(params.get("continue_on_ticker_failure"))
        include_portfolio_holdings = params.get("include_portfolio_holdings", True)
        root_run_id = self._root_run_id(run_id, params)
        execution_key = self._execution_key(run_id, params)

        params = {**params, "run_id": root_run_id}
        store = create_report_store(run_id=root_run_id)

        self._start_run_logger(root_run_id, logger_key=execution_key)
        try:
            logger.info("Starting AUTO run=%s date=%s force=%s", root_run_id, date, force)
            yield self._system_log(f'Starting full auto workflow for {date} (force={force}, run={root_run_id})')

            # Phase 1: Market scan
            yield self._system_log("Phase 1/3: Running market scan…")
            if not force and store.load_scan(date):
                yield self._system_log(f"Phase 1: Macro scan for {date} already exists, skipping.")
            else:
                scan_params = {"date": date, "run_id": root_run_id, "_execution_key": f"{root_run_id}:scan"}
                if params.get("max_tickers"):
                    scan_params["max_tickers"] = params["max_tickers"]
                try:
                    async for evt in self.run_scan(f"{root_run_id}:scan", scan_params):
                        yield evt
                except Exception as exc:
                    if _is_fallback_eligible_error(exc):
                        fallback_config = _build_fallback_config(self.config)
                        if fallback_config:
                            fallback_models = _fallback_model_summary(self.config, fallback_config)
                            await asyncio.sleep(0)
                            yield self._system_log(
                                "Phase 1/3: primary scan model unavailable — retrying with "
                                f"fallback: {fallback_models or 'configured tier fallbacks'}…"
                            )
                            original_config = self.config
                            self.config = fallback_config
                            try:
                                async for evt in self.run_scan(
                                    f"{root_run_id}:scan:fallback",
                                    {
                                        **scan_params,
                                        "_execution_key": f"{root_run_id}:scan:fallback",
                                    },
                                ):
                                    yield evt
                            finally:
                                self.config = original_config
                        else:
                            raise
                    else:
                        raise
            scan_state = self._load_scan_state(root_run_id=root_run_id, date=date, store=store)

            async for evt in self._run_auto_after_scan(
                root_run_id=root_run_id,
                date=date,
                force=force,
                params=params,
                store=store,
                scan_state=scan_state,
                continue_on_ticker_failure=continue_on_ticker_failure,
                include_portfolio_holdings=include_portfolio_holdings,
            ):
                yield evt

            logger.info("Completed AUTO run=%s", root_run_id)
        finally:
            self._finish_run_logger(execution_key, get_daily_dir(date, root_run_id))

    def _load_scan_state(self, *, root_run_id: str, date: str, store) -> Dict[str, Any]:
        """Load persisted Phase 1 reports into the state shape expected by Phase 2."""
        scan_state: Dict[str, Any] = {"scan_date": date}
        save_dir = get_market_dir(date, root_run_id)
        for key in SCAN_NODE_TO_REPORT_FIELD.values():
            report_file = save_dir / f"{key}.md"
            if report_file.exists():
                scan_state[key] = report_file.read_text()

        scan_summary = store.load_scan(date)
        if scan_summary:
            scan_state["macro_scan_summary"] = scan_summary
        return scan_state

    async def _run_auto_after_scan(
        self,
        *,
        root_run_id: str,
        date: str,
        force: bool,
        params: Dict[str, Any],
        store,
        scan_state: Dict[str, Any],
        continue_on_ticker_failure: bool,
        include_portfolio_holdings: bool,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        if _run_should_stop(root_run_id):
            yield self._system_log("Graceful stop requested — finishing after the market scan phase.")
            return

        # Phase 2: Pipeline analysis — get tickers from scan report + portfolio holdings
        yield self._system_log("Phase 2/3: Loading stocks from scan report…")
        scan_data = self._normalize_scan_summary(store.load_scan(date) or {})
        scan_instruments = self._extract_pipeline_instruments_from_scan_data(scan_data)
        tracked_market_symbols = [
            str(item.get("ticker") or "")
            for item in (scan_data.get("tracked_market_instruments") or [])
            if isinstance(item, dict)
        ]
        tracked_crypto_symbols = [
            str(item.get("ticker") or "")
            for item in (scan_data.get("tracked_crypto_instruments") or [])
            if isinstance(item, dict)
        ]

        # Safety cap: truncate scan candidates to max_auto_tickers (portfolio holdings added after)
        max_t = int(params.get("max_tickers") or self.config.get("max_auto_tickers") or 10)
        scan_instruments = scan_instruments[:max_t]

        # Also include tickers from current portfolio holdings so the PM agent
        # has fresh analysis for existing positions (hold/sell/add decisions).
        portfolio_id = params.get("portfolio_id", "main_portfolio")
        holding_tickers: list[str] = []
        if include_portfolio_holdings:
            try:
                from tradingagents.portfolio.repository import PortfolioRepository
                _repo = PortfolioRepository()
                _, holdings = _repo.get_portfolio_with_holdings(portfolio_id)
                holding_tickers = [h.ticker.upper() for h in holdings]
            except Exception as exc:
                logger.warning("run_auto: could not load holdings for pipeline: %s", exc)
        else:
            yield self._system_log(
                "Phase 2/3: include_portfolio_holdings=False — skipping portfolio holdings, scan candidates only."
            )

        holding_instruments = [
            resolve_instrument(ticker, source_context="holding")
            for ticker in holding_tickers
        ]
        holding_instrument_keys = {
            instrument.instrument_key
            for instrument in holding_instruments
            if is_equity_pipeline_supported(instrument)
        }
        skipped_holding_symbols = [
            instrument.canonical_symbol
            for instrument in holding_instruments
            if instrument.canonical_symbol and not is_equity_pipeline_supported(instrument)
        ]

        # Merge & deduplicate (scan candidates first, then holdings-only tickers)
        seen: set[str] = set()
        queued_instruments: list[CanonicalInstrument] = []
        for instrument in scan_instruments:
            if instrument.instrument_key not in seen:
                seen.add(instrument.instrument_key)
                queued_instruments.append(instrument)
        holdings_only: list[str] = []
        for instrument in holding_instruments:
            if not is_equity_pipeline_supported(instrument):
                continue
            if instrument.instrument_key not in seen:
                seen.add(instrument.instrument_key)
                queued_instruments.append(instrument)
                holdings_only.append(instrument.canonical_symbol)

        if scan_instruments:
            yield self._system_log(
                f"Phase 2/3: {len(scan_instruments)} equity ticker(s) from scan report"
            )
        if tracked_market_symbols:
            yield self._system_log(
                "Phase 2/3: tracked market instruments kept out of stock deep-dive queue: "
                + ", ".join(tracked_market_symbols)
            )
        if tracked_crypto_symbols:
            yield self._system_log(
                "Phase 2/3: tracked crypto instruments kept out of stock deep-dive queue: "
                + ", ".join(tracked_crypto_symbols)
            )
        if holdings_only:
            yield self._system_log(
                f"Phase 2/3: {len(holdings_only)} additional ticker(s) from portfolio holdings: "
                + ", ".join(holdings_only)
            )
        if skipped_holding_symbols:
            yield self._system_log(
                "Phase 2/3: skipping non-stock holdings for the current deep-dive path: "
                + ", ".join(sorted(set(skipped_holding_symbols)))
            )
        if not queued_instruments:
            yield self._system_log(
                "Warning: no common-stock candidates found in scan summary and no supported portfolio holdings — "
                "ensure the scan completed successfully and produced a "
                "stocks_to_investigate list. Skipping pipeline phase."
            )
        else:
            max_concurrent = int(self.config.get("max_concurrent_pipelines", 2))
            failed_tickers: dict[str, str] = {}
            completed_tickers: list[str] = []
            aborted_tickers: list[str] = []
            yield self._system_log(
                f"Phase 2/3: Queuing {len(queued_instruments)} ticker(s) "
                f"(max {max_concurrent} concurrent)…"
            )

            # Keep the producer and per-ticker pipelines inside task groups so
            # stop/cancel/exception paths cannot leave orphan LLM work behind.
            _sentinel = object()
            pipeline_queue: asyncio.Queue = asyncio.Queue()
            scheduler_error: str | None = None

            async def _run_one_ticker(instrument: CanonicalInstrument) -> None:
                ticker = instrument.canonical_symbol

                def _record_failure(reason: str) -> None:
                    failed_tickers[ticker] = reason

                existing_analysis = store.load_analysis(date, ticker)
                if not force and _analysis_is_terminal(existing_analysis):
                    status = _analysis_status(existing_analysis)
                    await pipeline_queue.put(
                        self._system_log(f"Phase 2: Analysis for {ticker} on {date} already exists, skipping.")
                    )
                    if status == "completed":
                        completed_tickers.append(ticker)
                    elif status == "aborted":
                        aborted_tickers.append(ticker)
                    return
                await pipeline_queue.put(
                    self._system_log(f"Phase 2/3: Running analysis pipeline for {ticker}…")
                )
                scanner_packet = self._build_scanner_context_packet(scan_state, ticker)

                try:
                    async for evt in self.run_pipeline(
                        f"{root_run_id}:pipeline:{ticker}",
                        {
                            "ticker": ticker,
                            "date": date,
                            "run_id": root_run_id,
                            "portfolio_context": "holding" if instrument.instrument_key in holding_instrument_keys else "candidate",
                            "scanner_context_packet": scanner_packet,
                            "_execution_key": f"{root_run_id}:pipeline:{ticker}",
                        },
                    ):
                        await pipeline_queue.put(evt)
                    saved_analysis = store.load_analysis(date, ticker)
                    saved_status = _analysis_status(saved_analysis)
                    if saved_status == "aborted":
                        aborted_tickers.append(ticker)
                        await pipeline_queue.put(
                            self._system_log(
                                f"Phase 2/3: {ticker} hit terminal critical-abort path ({saved_analysis.get('terminal_action', 'ABORT')})."
                            )
                        )
                    elif saved_status == "completed":
                        completed_tickers.append(ticker)
                    else:
                        reason = "analysis finished without a completed deep-dive decision"
                        _record_failure(reason)
                        await pipeline_queue.put(
                            self._system_log(
                                f"Warning: pipeline for {ticker} produced no deep-dive decision; skipping ticker in portfolio stage."
                            )
                        )
                except Exception as exc:
                    if _is_fallback_eligible_error(exc):
                        logger.error(
                            "Pipeline primary model unavailable ticker=%s run=%s: %s",
                            ticker,
                            root_run_id,
                            exc,
                        )
                        fallback_config = _build_fallback_config(self.config)
                        if fallback_config:
                            fallback_models = _fallback_model_summary(self.config, fallback_config)
                            await pipeline_queue.put(
                                self._system_log(
                                    f"Primary model unavailable for {ticker} — retrying with "
                                    f"fallback: {fallback_models or 'configured tier fallbacks'}…"
                                )
                            )
                            original_config = self.config
                            self.config = fallback_config
                            try:
                                async for evt in self.run_pipeline(
                                    f"{root_run_id}:fallback:{ticker}",
                                    {
                                        "ticker": ticker,
                                        "date": date,
                                        "run_id": root_run_id,
                                        "portfolio_context": "holding" if instrument.instrument_key in holding_instrument_keys else "candidate",
                                        "scanner_context_packet": scanner_packet,
                                        "_execution_key": f"{root_run_id}:fallback:{ticker}",
                                    },
                                ):
                                    await pipeline_queue.put(evt)
                                saved_analysis = store.load_analysis(date, ticker)
                                saved_status = _analysis_status(saved_analysis)
                                if saved_status == "aborted":
                                    aborted_tickers.append(ticker)
                                    await pipeline_queue.put(
                                        self._system_log(
                                            f"Phase 2/3: {ticker} hit terminal critical-abort path ({saved_analysis.get('terminal_action', 'ABORT')})."
                                        )
                                    )
                                elif saved_status == "completed":
                                    completed_tickers.append(ticker)
                                else:
                                    reason = "fallback finished without a completed deep-dive decision"
                                    _record_failure(reason)
                                    await pipeline_queue.put(
                                        self._system_log(
                                            f"Warning: fallback pipeline for {ticker} produced no deep-dive decision; skipping ticker in portfolio stage."
                                        )
                                    )
                            except Exception as fallback_exc:
                                logger.error(
                                    "Fallback pipeline failed ticker=%s: %s",
                                    ticker, fallback_exc,
                                )
                                _record_failure(str(fallback_exc))
                                await pipeline_queue.put(
                                    self._system_log(
                                        f"Warning: pipeline for {ticker} failed "
                                        f"(fallback also failed): {fallback_exc}"
                                    )
                                )
                            finally:
                                self.config = original_config
                        else:
                            _record_failure(str(exc))
                            await pipeline_queue.put(
                                self._system_log(
                                    f"Warning: pipeline for {ticker} failed due to LLM provider availability. "
                                    f"{exc} — "
                                    f"Set TRADINGAGENTS_QUICK_THINK_FALLBACK_LLM (and MID/DEEP) "
                                    f"to auto-retry with a different model."
                                )
                            )
                    else:
                        logger.exception(
                            "Pipeline failed ticker=%s run=%s", ticker, root_run_id
                        )
                        _record_failure(str(exc))
                        await pipeline_queue.put(
                            self._system_log(
                                f"Warning: pipeline for {ticker} failed: {exc}"
                            )
                        )

            async def _pipeline_producer() -> None:
                nonlocal scheduler_error
                stop_logged = False

                try:
                    async with asyncio.TaskGroup() as ticker_group:
                        pending: set[asyncio.Task] = set()
                        iterator = iter(queued_instruments)

                        def _forget_task(task: asyncio.Task) -> None:
                            pending.discard(task)

                        while True:
                            while len(pending) < max_concurrent:
                                if _run_should_stop(root_run_id):
                                    if not stop_logged:
                                        stop_logged = True
                                        await pipeline_queue.put(
                                            self._system_log(
                                                "Graceful stop requested — no new ticker pipelines will be queued."
                                            )
                                        )
                                    break
                                try:
                                    instrument = next(iterator)
                                except StopIteration:
                                    break
                                task = ticker_group.create_task(_run_one_ticker(instrument))
                                pending.add(task)
                                task.add_done_callback(_forget_task)

                            if not pending:
                                break

                            done, _ = await asyncio.wait(
                                tuple(pending),
                                return_when=asyncio.FIRST_COMPLETED,
                            )
                            for task in done:
                                await task
                except Exception as exc:
                    scheduler_error = str(exc)
                    logger.exception("Pipeline scheduler failed run=%s", root_run_id)
                    failed_tickers["<scheduler>"] = str(exc)
                finally:
                    await pipeline_queue.put(_sentinel)

            generator_closed = False
            try:
                async with asyncio.TaskGroup() as producer_group:
                    producer_group.create_task(_pipeline_producer())
                    while True:
                        item = await pipeline_queue.get()
                        if item is _sentinel:
                            break
                        yield item
            except* GeneratorExit:
                generator_closed = True

            if generator_closed:
                return

            if failed_tickers:
                failed_summary = ", ".join(
                    f"{ticker} ({reason})" for ticker, reason in sorted(failed_tickers.items())
                )
                if continue_on_ticker_failure:
                    yield self._system_log(
                        "Phase 2/3: continuing to portfolio stage without failed tickers: "
                        + failed_summary
                    )
                else:
                    yield self._system_log(
                        "Phase 2/3: paused before portfolio stage because ticker analyses failed: "
                        + failed_summary
                    )
                    ticker_contexts = {
                        instrument.canonical_symbol: (
                            "holding" if instrument.instrument_key in holding_instrument_keys else "candidate"
                        )
                        for instrument in queued_instruments
                    }
                    raise AwaitPhase3Decision(
                        {
                            "date": date,
                            "portfolio_id": portfolio_id,
                            "incomplete_tickers": [
                                {
                                    "ticker": ticker,
                                    "reason": reason,
                                    "portfolio_context": ticker_contexts.get(ticker, "candidate"),
                                }
                                for ticker, reason in sorted(failed_tickers.items())
                                if ticker != "<scheduler>"
                            ],
                            "completed_tickers": sorted(completed_tickers),
                            "aborted_tickers": sorted(aborted_tickers),
                            "scheduler_error": scheduler_error,
                        }
                    )

        if _run_should_stop(root_run_id):
            yield self._system_log("Graceful stop requested — finishing after Phase 2 without starting portfolio management.")
            return

        async for evt in self._run_auto_phase_three(
            root_run_id=root_run_id,
            date=date,
            force=force,
            params=params,
            store=store,
        ):
            yield evt

    async def run_auto_from_scan_rerun(
        self,
        run_id: str,
        params: Dict[str, Any],
        start_node: str,
        initial_state: Dict[str, Any],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Continue an auto workflow after re-running part of the market scan."""
        date = params.get("date", time.strftime("%Y-%m-%d"))
        force = params.get("force", False)
        continue_on_ticker_failure = bool(params.get("continue_on_ticker_failure"))
        include_portfolio_holdings = params.get("include_portfolio_holdings", True)
        root_run_id = self._root_run_id(run_id, params)
        store = create_report_store(run_id=root_run_id)

        scan_params = {
            "date": date,
            "portfolio_id": params.get("portfolio_id", "main_portfolio"),
            "run_id": root_run_id,
            "max_tickers": params.get("max_tickers"),
            "_execution_key": f"{root_run_id}:scan-rerun:{start_node}",
        }
        async for evt in self.run_scan_from_node(
            f"{root_run_id}:scan-rerun:{start_node}",
            scan_params,
            start_node,
            initial_state,
        ):
            yield evt

        scan_state = self._load_scan_state(root_run_id=root_run_id, date=date, store=store)
        async for evt in self._run_auto_after_scan(
            root_run_id=root_run_id,
            date=date,
            force=force,
            params={**params, "run_id": root_run_id},
            store=store,
            scan_state=scan_state,
            continue_on_ticker_failure=continue_on_ticker_failure,
            include_portfolio_holdings=include_portfolio_holdings,
        ):
            yield evt

    async def _run_auto_phase_three(
        self,
        *,
        root_run_id: str,
        date: str,
        force: bool,
        params: Dict[str, Any],
        store,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Run or resume the portfolio stage for an auto workflow."""
        yield self._system_log("Phase 3/3: Running portfolio manager…")
        portfolio_params = {k: v for k, v in params.items() if k != "ticker"}
        portfolio_params["run_id"] = root_run_id
        portfolio_id = params.get("portfolio_id", "main_portfolio")

        # Check if portfolio stage is fully complete (execution result exists)
        if not force and store.load_execution_result(date, portfolio_id):
            yield self._system_log(
                f"Phase 3: Portfolio execution for {portfolio_id} on {date} already exists, skipping."
            )
        else:
            # Check if we can resume from a saved decision
            saved_decision = store.load_pm_decision(date, portfolio_id)
            if not force and saved_decision:
                yield self._system_log(
                    f"Phase 3: Found saved PM decision for {portfolio_id}, resuming trade execution…"
                )
                prices = _fetch_prices(_tickers_from_decision(saved_decision))
                async for evt in self.run_trade_execution(
                    root_run_id,
                    date,
                    portfolio_id,
                    saved_decision,
                    prices,
                    store=store,
                ):
                    yield evt
            else:
                async for evt in self.run_portfolio(
                    f"{root_run_id}:portfolio",
                    {
                        "date": date,
                        **portfolio_params,
                        "_execution_key": f"{root_run_id}:portfolio",
                    },
                ):
                    yield evt

    async def run_auto_phase3_decision(
        self,
        run_id: str,
        params: Dict[str, Any],
        retry_tickers: list[str],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Resolve an auto-run Phase 2 pause by retrying selected tickers or continuing."""
        root_run_id = self._root_run_id(run_id, params)
        execution_key = self._execution_key(run_id, params)
        date = params.get("date", time.strftime("%Y-%m-%d"))
        force = bool(params.get("force", False))
        store = create_report_store(run_id=root_run_id)
        run_record = live_runs.get(root_run_id) or {}
        pending = run_record.get("pending_phase3_decision") or {}
        incomplete = pending.get("incomplete_tickers") or []
        portfolio_id = pending.get("portfolio_id") or params.get("portfolio_id", "main_portfolio")
        self._start_run_logger(root_run_id, logger_key=execution_key)

        try:
            if not incomplete:
                raise ValueError("No incomplete ticker analyses are waiting for a Phase 3 decision.")

            incomplete_map = {
                str(item.get("ticker") or "").upper(): item
                for item in incomplete
                if isinstance(item, dict) and item.get("ticker")
            }
            invalid = [ticker for ticker in retry_tickers if ticker not in incomplete_map]
            if invalid:
                raise ValueError(
                    "Retry tickers are not in the current incomplete set: " + ", ".join(sorted(invalid))
                )

            if retry_tickers:
                yield self._system_log(
                    "Phase 2/3: retrying selected incomplete ticker(s): "
                    + ", ".join(sorted(retry_tickers))
                )
                for ticker in retry_tickers:
                    if _run_should_stop(root_run_id):
                        logger.info("AUTO_PHASE3_DECISION run=%s: graceful stop requested, aborting early", root_run_id)
                        yield self._system_log("Aborting retry due to graceful stop request.")
                        raise asyncio.CancelledError()
                    item = incomplete_map[ticker]
                    async for evt in self.run_pipeline(
                        f"{root_run_id}:decision-retry:{ticker}",
                        {
                            "ticker": ticker,
                            "date": date,
                            "run_id": root_run_id,
                            "portfolio_context": item.get("portfolio_context", "candidate"),
                            "_execution_key": f"{root_run_id}:decision-retry:{ticker}",
                        },
                    ):
                        yield evt

                remaining_incomplete: list[dict[str, str]] = []
                completed_tickers: list[str] = []
                aborted_tickers: list[str] = []
                for ticker, item in sorted(incomplete_map.items()):
                    analysis = store.load_analysis(date, ticker)
                    status = _analysis_status(analysis)
                    if status == "completed":
                        completed_tickers.append(ticker)
                    elif status == "aborted":
                        aborted_tickers.append(ticker)
                    else:
                        remaining_incomplete.append(
                            {
                                "ticker": ticker,
                                "reason": "analysis finished without a completed deep-dive decision"
                                if status == "missing"
                                else f"analysis artifact remained {status}",
                                "portfolio_context": item.get("portfolio_context", "candidate"),
                            }
                        )

                if remaining_incomplete:
                    failed_summary = ", ".join(
                        f"{item['ticker']} ({item['reason']})" for item in remaining_incomplete
                    )
                    yield self._system_log(
                        "Phase 2/3: paused again before portfolio stage because ticker analyses are still incomplete: "
                        + failed_summary
                    )
                    raise AwaitPhase3Decision(
                        {
                            "date": date,
                            "portfolio_id": portfolio_id,
                            "incomplete_tickers": remaining_incomplete,
                            "completed_tickers": sorted(set((pending.get("completed_tickers") or []) + completed_tickers)),
                            "aborted_tickers": sorted(set((pending.get("aborted_tickers") or []) + aborted_tickers)),
                            "scheduler_error": None,
                        }
                    )

            else:
                yield self._system_log(
                    "Phase 2/3: continuing to Phase 3 without retrying incomplete tickers."
                )

            async for evt in self._run_auto_phase_three(
                root_run_id=root_run_id,
                date=date,
                force=force,
                params={**params, "portfolio_id": portfolio_id, "run_id": root_run_id},
                store=store,
            ):
                yield evt
        finally:
            self._finish_run_logger(execution_key, get_daily_dir(date, root_run_id))

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
        Returns a deduplicated list of common-stock symbols in original order.
        """
        if not scan_data:
            return []
        raw_stocks = scan_data.get("equity_candidates") or scan_data.get("stocks_to_investigate") or scan_data.get("watchlist") or []
        seen: set[str] = set()
        tickers: list[str] = []
        for item in raw_stocks:
            if isinstance(item, dict):
                sym = item.get("ticker") or item.get("symbol") or ""
            elif isinstance(item, str):
                sym = item
            else:
                continue
            instrument = resolve_instrument(sym, source_context="scan")
            if not is_equity_pipeline_supported(instrument):
                continue
            if instrument.canonical_symbol and instrument.canonical_symbol not in seen:
                seen.add(instrument.canonical_symbol)
                tickers.append(instrument.canonical_symbol)
        return tickers

    @staticmethod
    def _extract_pipeline_instruments_from_scan_data(scan_data: Dict[str, Any] | None) -> list[CanonicalInstrument]:
        if not scan_data:
            return []
        raw_stocks = scan_data.get("equity_candidates") or scan_data.get("stocks_to_investigate") or scan_data.get("watchlist") or []
        seen: set[str] = set()
        instruments: list[CanonicalInstrument] = []
        for item in raw_stocks:
            if isinstance(item, dict):
                sym = item.get("ticker") or item.get("symbol") or ""
            elif isinstance(item, str):
                sym = item
            else:
                continue
            instrument = resolve_instrument(sym, source_context="scan")
            if not is_equity_pipeline_supported(instrument):
                continue
            if instrument.instrument_key in seen:
                continue
            seen.add(instrument.instrument_key)
            instruments.append(instrument)
        return instruments

    @staticmethod
    def _normalize_scan_summary(scan_data: Dict[str, Any] | None) -> Dict[str, Any]:
        if not isinstance(scan_data, dict):
            return {}
        normalized = dict(scan_data)
        raw_stocks = normalized.get("stocks_to_investigate") or normalized.get("watchlist")
        if raw_stocks is None:
            raw_stocks = normalized.get("equity_candidates") or []
        equity_candidates: list[dict[str, Any]] = []
        tracked_market_instruments: list[dict[str, Any]] = []
        tracked_crypto_instruments: list[dict[str, Any]] = []
        for item in raw_stocks:
            if isinstance(item, dict):
                candidate = dict(item)
                sym = candidate.get("ticker") or candidate.get("symbol") or ""
            elif isinstance(item, str):
                sym = item
                candidate = {"ticker": str(item).strip().upper()}
            else:
                continue
            instrument = resolve_instrument(sym, source_context="scan")
            candidate.update(instrument.to_metadata())
            candidate["ticker"] = instrument.canonical_symbol
            if is_equity_pipeline_supported(instrument):
                equity_candidates.append(candidate)
            elif instrument.asset_class in {"etf", "index"}:
                tracked_market_instruments.append(candidate)
            elif instrument.asset_class == "crypto":
                tracked_crypto_instruments.append(candidate)
        normalized["equity_candidates"] = equity_candidates
        normalized["tracked_market_instruments"] = tracked_market_instruments
        normalized["tracked_crypto_instruments"] = tracked_crypto_instruments
        return normalized

    @staticmethod
    def _build_scanner_context_packet(scan_state: Dict[str, Any], ticker: str) -> str:
        """Consolidate Phase 1 scanner output into a clinical context packet for Phase 2."""
        ticker = ticker.upper()
        
        # 1. Ticker-specific thesis from synthesis
        macro_summary = scan_state.get("macro_scan_summary", "")
        ticker_thesis = "No specific scanner thesis found for this ticker."
        key_themes = "None"
        risk_factors = "None"
        
        try:
            summary_data = extract_json(macro_summary) if isinstance(macro_summary, str) else macro_summary
            if isinstance(summary_data, dict):
                candidates = summary_data.get("stocks_to_investigate") or summary_data.get("equity_candidates") or []
                for c in candidates:
                    c_ticker = (c.get("ticker") or c.get("symbol") or "").upper()
                    if c_ticker == ticker:
                        ticker_thesis = (
                            f"Rationale: {c.get('rationale', 'N/A')}\n"
                            f"Thesis Angle: {c.get('thesis_angle', 'N/A')}\n"
                            f"Conviction: {c.get('conviction', 'N/A')}\n"
                            f"Key Catalysts: {', '.join(c.get('key_catalysts', []))}\n"
                            f"Specific Risks: {', '.join(c.get('risks', []))}"
                        )
                        break
                
                themes = summary_data.get("key_themes", [])
                if themes:
                    key_themes = "\n".join([f"- {t.get('theme')}: {t.get('description')} (Conviction: {t.get('conviction')})" for t in themes])
                
                risks = summary_data.get("risk_factors", [])
                if risks:
                    risk_factors = "\n".join([f"- {r}" for r in risks])
        except Exception:
            logger.warning("Failed to parse macro_scan_summary for scanner context packet")

        # 2. Extract specific reports
        geo_report = scan_state.get("geopolitical_report", "N/A")
        smart_money = scan_state.get("smart_money_report", "N/A")
        factor_alignment = scan_state.get("factor_alignment_report", "N/A")
        sector_performance = scan_state.get("sector_performance_report", "N/A")
        drift_report = scan_state.get("drift_opportunities_report", "N/A")

        # 3. Fetch structured live data to prevent hallucinations
        gold = "N/A"
        oil = "N/A"
        btc = "N/A"
        fx = "N/A"
        earnings = "N/A"
        economics = "N/A"

        try:
            gold = get_gold_price.invoke({})
            oil = get_oil_prices.invoke({})
            btc = get_bitcoin_price.invoke({})
            eur = get_eur_usd_rate.invoke({})
            jpy = get_jpy_usd_rate.invoke({})
            cny = get_cny_usd_rate.invoke({})
            fx = f"{eur}\n{jpy}\n{cny}"
            
            scan_date_str = scan_state.get('scan_date', time.strftime("%Y-%m-%d"))
            scan_dt = _dt.datetime.strptime(scan_date_str, "%Y-%m-%d")
            from_date = (scan_dt - _dt.timedelta(days=7)).strftime("%Y-%m-%d")
            to_date = (scan_dt + _dt.timedelta(days=14)).strftime("%Y-%m-%d")
            
            earnings = get_earnings_calendar.invoke({"from_date": from_date, "to_date": to_date})
            economics = get_economic_calendar.invoke({"from_date": from_date, "to_date": to_date})
        except Exception as e:
            logger.warning(f"Failed to fetch structured data for scanner context packet: {e}")

        packet = f"""# SCANNER CONTEXT PACKET: {ticker}
Date: {scan_state.get('scan_date', 'N/A')}

## I. TICKER-SPECIFIC SCANNER THESIS
{ticker_thesis}

## II. STRUCTURED LIVE DATA (GROUND TRUTH)
### Commodity Prices
{gold}
{oil}
{btc}

### FX Rates
{fx}

### Earnings Calendar (7d lookback, 14d lookahead)
{earnings}

### Economic Calendar (7d lookback, 14d lookahead)
{economics}

## III. SMART MONEY & FLOW SIGNALS
{smart_money}

## IV. FACTOR ALIGNMENT & DRIFT
{factor_alignment}
{drift_report}

## V. MACRO & GEOPOLITICAL CONTEXT
{geo_report}

## VI. SECTOR ROTATION & MARKET REGIME
{sector_performance}

## VII. KEY GLOBAL THEMES
{key_themes}

## VIII. MACRO RISK FACTORS
{risk_factors}
"""
        return packet

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
