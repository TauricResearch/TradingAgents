# TradingAgents/graph/trading_graph.py

import logging
import os
from pathlib import Path
import json
import asyncio
import queue
import requests
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Tuple, List, Optional

import yfinance as yf

logger = logging.getLogger(__name__)

from langgraph.prebuilt import ToolNode

from tradingagents.llm_clients import create_llm_client

from tradingagents.agents import *
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.utils.memory import TradingMemoryLog
from tradingagents.dataflows.utils import safe_ticker_component
from tradingagents.agents.utils.agent_states import (
    AgentState,
    InvestDebateState,
    RiskDebateState,
)
from tradingagents.dataflows.config import set_config

# Import the new abstract tool methods from agent_utils
from tradingagents.agents.utils.agent_utils import (
    get_stock_data,
    get_indicators,
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement,
    get_news,
    get_insider_transactions,
    get_global_news
)

from .checkpointer import checkpoint_step, clear_checkpoint, get_checkpointer, thread_id
from .conditional_logic import ConditionalLogic
from .setup import GraphSetup
from .propagation import Propagator
from .reflection import Reflector
from .signal_processing import SignalProcessor


class _WebhookDispatcher:
    """Background dispatcher for progress webhooks.

    This keeps dashboard updates off the graph critical path and reduces the
    chance that a slow UI service stretches analyst runtime.
    """

    def __init__(self, webhook_url: Optional[str], max_queue_size: int = 128):
        self.webhook_url = webhook_url
        self._queue: queue.Queue = queue.Queue(maxsize=max_queue_size)
        self._stop = object()
        self._thread = None
        self._session = requests.Session() if webhook_url else None

        if webhook_url:
            self._thread = threading.Thread(
                target=self._worker,
                name="tradingagents-webhook-dispatcher",
                daemon=True,
            )
            self._thread.start()

    def enqueue(self, payload: Dict[str, Any]) -> None:
        if not self.webhook_url:
            return
        try:
            self._queue.put_nowait(payload)
        except queue.Full:
            # Drop noisy in-progress updates first; terminal events should still go through.
            if payload.get("status") == "in_progress":
                logger.warning("Dropping in-progress webhook update because queue is full")
                return
            try:
                self._queue.put(payload, timeout=1)
            except queue.Full:
                logger.warning("Dropping terminal webhook update because queue remained full")

    def flush(self, timeout: float = 5.0) -> None:
        if not self.webhook_url:
            return
        self._queue.join()
        if self._thread:
            self._queue.put(self._stop)
            self._thread.join(timeout=timeout)

    def _worker(self) -> None:
        while True:
            payload = self._queue.get()
            try:
                if payload is self._stop:
                    return
                self._session.post(self.webhook_url, json=payload, timeout=2)
            except Exception as e:
                logger.warning("Failed to send webhook update: %s", e)
            finally:
                self._queue.task_done()


class TradingAgentsGraph:
    """Main class that orchestrates the trading agents framework."""

    def __init__(
        self,
        selected_analysts=["market", "social", "news", "fundamentals"],
        debug=False,
        config: Dict[str, Any] = None,
        callbacks: Optional[List] = None,
    ):
        """Initialize the trading agents graph and components."""
        self.debug = debug
        self.config = config or DEFAULT_CONFIG
        self.callbacks = callbacks or []
        self.run_id = self.config.get("run_id")
        self.webhook_url = self.config.get("webhook_url") or os.getenv("TRADINGAGENTS_WEBHOOK_URL")

        # Configure logging based on config
        log_level = self.config.get("log_level", "INFO").upper()
        logging.basicConfig(level=getattr(logging, log_level, logging.INFO))
        
        # Update the interface's config
        set_config(self.config)

        # Create necessary directories
        os.makedirs(self.config["data_cache_dir"], exist_ok=True)
        os.makedirs(self.config["results_dir"], exist_ok=True)

        # Initialize LLMs with provider-specific thinking configuration
        llm_kwargs = self._get_provider_kwargs()

        # Add callbacks to kwargs if provided (passed to LLM constructor)
        if self.callbacks:
            llm_kwargs["callbacks"] = self.callbacks

        deep_client = create_llm_client(
            provider=self.config["llm_provider"],
            model=self.config["deep_think_llm"],
            base_url=self.config.get("backend_url"),
            **llm_kwargs,
        )
        quick_client = create_llm_client(
            provider=self.config["llm_provider"],
            model=self.config["quick_think_llm"],
            base_url=self.config.get("backend_url"),
            **llm_kwargs,
        )

        self.deep_thinking_llm = deep_client.get_llm()
        self.quick_thinking_llm = quick_client.get_llm()
        
        self.memory_log = TradingMemoryLog(self.config)

        # Create tool nodes
        self.tool_nodes = self._create_tool_nodes()

        # Initialize components
        self.conditional_logic = ConditionalLogic(
            max_debate_rounds=self.config["max_debate_rounds"],
            max_risk_discuss_rounds=self.config["max_risk_discuss_rounds"],
        )
        self.graph_setup = GraphSetup(
            self.quick_thinking_llm,
            self.deep_thinking_llm,
            self.tool_nodes,
            self.conditional_logic,
        )

        self.propagator = Propagator(
            max_recur_limit=self.config.get("max_recur_limit", 100),
        )
        self.reflector = Reflector(self.quick_thinking_llm)
        self.signal_processor = SignalProcessor(self.quick_thinking_llm)
        self.webhook_dispatcher = _WebhookDispatcher(
            self.webhook_url,
            max_queue_size=self.config.get("webhook_queue_size", 128),
        )

        # State tracking
        self.curr_state = None
        self.ticker = None
        self.log_states_dict = {}  # date to full state dict
        self.run_timing = {}

        # Set up the graph: keep the workflow for recompilation with a checkpointer.
        self.workflow = self.graph_setup.setup_graph(
            selected_analysts, standalone=self.config.get("standalone", False)
        )
        self.graph = self.workflow.compile()
        self._checkpointer_ctx = None

    def _get_provider_kwargs(self) -> Dict[str, Any]:
        """Get provider-specific kwargs for LLM client creation."""
        kwargs = {}
        provider = self.config.get("llm_provider", "").lower()

        if provider == "google":
            thinking_level = self.config.get("google_thinking_level")
            if thinking_level:
                kwargs["thinking_level"] = thinking_level

        elif provider == "openai":
            reasoning_effort = self.config.get("openai_reasoning_effort")
            if reasoning_effort:
                kwargs["reasoning_effort"] = reasoning_effort

        elif provider == "anthropic":
            effort = self.config.get("anthropic_effort")
            if effort:
                kwargs["effort"] = effort

        return kwargs

    def _create_tool_nodes(self) -> Dict[str, ToolNode]:
        """Create tool nodes for different data sources using abstract methods."""
        return {
            "market": ToolNode(
                [
                    # Core stock data tools
                    get_stock_data,
                    # Technical indicators
                    get_indicators,
                ],
                messages_key="market_messages"
            ),
            "social": ToolNode(
                [
                    # News tools for social media analysis
                    get_news,
                ],
                messages_key="sentiment_messages"
            ),
            "news": ToolNode(
                [
                    # News and insider information
                    get_news,
                    get_global_news,
                    get_insider_transactions,
                ],
                messages_key="news_messages"
            ),
            "fundamentals": ToolNode(
                [
                    # Fundamental analysis tools
                    get_fundamentals,
                    get_balance_sheet,
                    get_cashflow,
                    get_income_statement,
                ],
                messages_key="fundamentals_messages"
            ),
        }

    def _resolve_benchmark(self, ticker: str) -> str:
        """Pick the benchmark ticker for alpha calculation against ``ticker``.

        ``config["benchmark_ticker"]`` overrides everything when set; otherwise
        the suffix map matches the ticker's exchange suffix (e.g. ``.T`` for
        Tokyo). US-listed tickers without a dotted suffix fall through to the
        empty-suffix entry (SPY by default). Unrecognised suffixes (including
        US tickers with dots like ``BRK.B``) also fall back to the empty-suffix
        entry, which is the right default because the alpha calculation works
        in USD.
        """
        explicit = self.config.get("benchmark_ticker")
        if explicit:
            return explicit
        benchmark_map = self.config.get("benchmark_map", {})
        ticker_upper = ticker.upper()
        for suffix, benchmark in benchmark_map.items():
            if suffix and ticker_upper.endswith(suffix.upper()):
                return benchmark
        return benchmark_map.get("", "SPY")

    def _fetch_returns(
        self, ticker: str, trade_date: str, holding_days: int = 5,
        benchmark: str = "SPY",
    ) -> Tuple[Optional[float], Optional[float], Optional[int]]:
        """Fetch raw and alpha return for ticker over holding_days from trade_date.

        ``benchmark`` is the index used as the alpha baseline (resolved by the
        caller via ``_resolve_benchmark``). Returns ``(raw_return, alpha_return,
        actual_holding_days)`` or ``(None, None, None)`` if price data is
        unavailable (too recent, delisted, or network error).
        """
        try:
            start = datetime.strptime(trade_date, "%Y-%m-%d")
            end = start + timedelta(days=holding_days + 7)  # buffer for weekends/holidays
            end_str = end.strftime("%Y-%m-%d")

            stock = yf.Ticker(ticker).history(start=trade_date, end=end_str)
            bench = yf.Ticker(benchmark).history(start=trade_date, end=end_str)

            if len(stock) < 2 or len(bench) < 2:
                return None, None, None

            actual_days = min(holding_days, len(stock) - 1, len(bench) - 1)
            raw = float(
                (stock["Close"].iloc[actual_days] - stock["Close"].iloc[0])
                / stock["Close"].iloc[0]
            )
            bench_ret = float(
                (bench["Close"].iloc[actual_days] - bench["Close"].iloc[0])
                / bench["Close"].iloc[0]
            )
            alpha = raw - bench_ret
            return raw, alpha, actual_days
        except Exception as e:
            logger.warning(
                "Could not resolve outcome for %s on %s vs %s (will retry next run): %s",
                ticker, trade_date, benchmark, e,
            )
            return None, None, None

    def _resolve_pending_entries(self, ticker: str) -> None:
        """Resolve pending log entries for ticker at the start of a new run.

        Fetches returns for each same-ticker pending entry, generates reflections,
        then writes all updates in a single atomic batch write to avoid redundant I/O.
        Skips entries whose price data is not yet available (too recent or delisted).

        Trade-off: only same-ticker entries are resolved per run.  Entries for
        other tickers accumulate until that ticker is run again.
        """
        pending = [e for e in self.memory_log.get_pending_entries() if e["ticker"] == ticker]
        if not pending:
            return

        benchmark = self._resolve_benchmark(ticker)
        updates = []
        for entry in pending:
            raw, alpha, days = self._fetch_returns(
                ticker, entry["date"], benchmark=benchmark,
            )
            if raw is None:
                continue  # price not available yet — try again next run
            reflection = self.reflector.reflect_on_final_decision(
                final_decision=entry.get("decision", ""),
                raw_return=raw,
                alpha_return=alpha,
                benchmark_name=benchmark,
            )
            updates.append({
                "ticker": ticker,
                "trade_date": entry["date"],
                "raw_return": raw,
                "alpha_return": alpha,
                "holding_days": days,
                "reflection": reflection,
            })

        if updates:
            self.memory_log.batch_update_with_outcomes(updates)

    def propagate(self, company_name, trade_date):
        """Run the trading agents graph for a company on a specific date.

        When ``checkpoint_enabled`` is set in config, the graph is recompiled
        with a per-ticker SqliteSaver so a crashed run can resume from the last
        successful node on a subsequent invocation with the same ticker+date.
        """
        self.ticker = company_name

        # Resolve any pending memory-log entries for this ticker before the pipeline runs.
        self._resolve_pending_entries(company_name)

        # Recompile with a checkpointer if the user opted in.
        if self.config.get("checkpoint_enabled"):
            self._checkpointer_ctx = get_checkpointer(
                self.config["data_cache_dir"], company_name
            )
            saver = self._checkpointer_ctx.__enter__()
            self.graph = self.workflow.compile(checkpointer=saver)

            step = checkpoint_step(
                self.config["data_cache_dir"], company_name, str(trade_date)
            )
            if step is not None:
                logger.info(
                    "Resuming from step %d for %s on %s", step, company_name, trade_date
                )
            else:
                logger.info("Starting fresh for %s on %s", company_name, trade_date)

        try:
            return self._run_graph(company_name, trade_date)
        finally:
            self.webhook_dispatcher.flush()
            if self._checkpointer_ctx is not None:
                self._checkpointer_ctx.__exit__(None, None, None)
                self._checkpointer_ctx = None
                self.graph = self.workflow.compile()

    def _run_graph(self, company_name, trade_date):
        """Run the graph using a checkpoint-compatible execution path."""
        if self.config.get("checkpoint_enabled"):
            return self._run_graph_sync(company_name, trade_date)
        return asyncio.run(self._run_graph_async(company_name, trade_date))

    def _init_run_timing(self, company_name, trade_date):
        """Create the shared timing payload used by sync and async runners."""
        return {
            "run_id": self.run_id,
            "ticker": company_name,
            "trade_date": str(trade_date),
            "total_runtime_seconds": None,
            "node_timings": {},
            "node_order": [],
        }

    def _record_node_timing(self, timing, node_name, now, node_elapsed):
        """Update timing stats for one streamed node event."""
        node_stats = timing["node_timings"].setdefault(
            node_name,
            {
                "count": 0,
                "observed_duration_seconds_total": 0.0,
                "observed_duration_seconds_last": 0.0,
                "completed_at": None,
            },
        )
        node_stats["count"] += 1
        node_stats["observed_duration_seconds_total"] += node_elapsed
        node_stats["observed_duration_seconds_last"] = node_elapsed
        node_stats["completed_at"] = now.isoformat() + "Z"
        timing["node_order"].append(node_name)
        logger.info("Node [%s] emitted update after %.2fs", node_name, node_elapsed)

    def _send_in_progress_webhook(
        self, company_name, trade_date, node_name, now, start_time_iso, node_updates, perf_start, timing
    ):
        """Send a standardized in-progress update for the current node."""
        self._send_webhook({
            "run_id": self.run_id,
            "ticker": company_name,
            "date": trade_date,
            "node": node_name,
            "status": "in_progress",
            "timestamp": now.isoformat() + "Z",
            "start_time": start_time_iso,
            "updates": node_updates,
            "timing": {
                "total_runtime_seconds": round(time.perf_counter() - perf_start, 3),
                "node_timings": timing["node_timings"],
                "latest_node": node_name,
            },
        })

    def _run_graph_sync(self, company_name, trade_date):
        """Execute the graph synchronously for checkpoint-compatible runs."""
        start_time = datetime.utcnow()
        start_time_iso = start_time.isoformat() + "Z"
        perf_start = time.perf_counter()
        timing = self._init_run_timing(company_name, trade_date)
        self._send_webhook({
            "run_id": self.run_id,
            "ticker": company_name,
            "date": trade_date,
            "node": "Initializing...",
            "status": "in_progress",
            "timestamp": start_time_iso,
            "start_time": start_time_iso,
            "timing": {
                "total_runtime_seconds": 0.0,
                "node_timings": {},
            },
        })

        past_context = self.memory_log.get_past_context(company_name)
        init_agent_state = self.propagator.create_initial_state(
            company_name, trade_date, past_context=past_context
        )
        self._send_webhook({
            "run_id": self.run_id,
            "ticker": company_name,
            "date": trade_date,
            "node": "Launching Analyst Branches...",
            "status": "in_progress",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "start_time": start_time_iso,
        })
        args = self.propagator.get_graph_args()
        config = args.get("config", {})
        if self.config.get("checkpoint_enabled"):
            tid = thread_id(company_name, str(trade_date))
            config.setdefault("configurable", {})["thread_id"] = tid
            args["config"] = config

        trace = []
        previous_chunk_at = perf_start

        try:
            for chunk in self.graph.stream(init_agent_state, **args):
                node_name = list(chunk.keys())[0] if chunk else "unknown"
                node_updates = chunk.get(node_name, {})
                now = datetime.utcnow()
                current_perf = time.perf_counter()
                node_elapsed = max(0.0, current_perf - previous_chunk_at)
                previous_chunk_at = current_perf
                self._record_node_timing(timing, node_name, now, node_elapsed)
                trace.append(chunk)
                self._send_in_progress_webhook(
                    company_name,
                    trade_date,
                    node_name,
                    now,
                    start_time_iso,
                    node_updates,
                    perf_start,
                    timing,
                )
        except Exception as e:
            logger.error("Error during sync graph execution for %s: %s", company_name, e)
            self._send_webhook({
                "run_id": self.run_id,
                "ticker": company_name,
                "date": trade_date,
                "status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "start_time": start_time_iso,
                "timing": {
                    "total_runtime_seconds": round(time.perf_counter() - perf_start, 3),
                    "node_timings": timing["node_timings"],
                },
            })
            raise

        final_state = self.graph.get_state(config).values
        self.curr_state = final_state
        end_time = datetime.utcnow()
        end_time_iso = end_time.isoformat() + "Z"
        timing["total_runtime_seconds"] = round(time.perf_counter() - perf_start, 3)
        self.run_timing = timing

        self._log_state(trade_date, final_state, start_time, end_time, timing)
        self._send_webhook({
            "run_id": self.run_id,
            "ticker": company_name,
            "date": trade_date,
            "status": "completed",
            "timestamp": end_time_iso,
            "start_time": start_time_iso,
            "end_time": end_time_iso,
            "timing": timing,
        })

        final_decision = final_state.get("final_trade_decision")
        if final_decision:
            self.memory_log.store_decision(
                ticker=company_name,
                trade_date=trade_date,
                final_trade_decision=final_decision,
            )

        if self.config.get("checkpoint_enabled"):
            clear_checkpoint(
                self.config["data_cache_dir"], company_name, str(trade_date)
            )

        return final_state, self.process_signal(final_decision) if final_decision else "N/A"

    async def _run_graph_async(self, company_name, trade_date):
        """Execute the graph and write the resulting state to disk and memory log."""
        start_time = datetime.utcnow()
        start_time_iso = start_time.isoformat() + "Z"
        perf_start = time.perf_counter()
        timing = self._init_run_timing(company_name, trade_date)
        # Notify starting
        self._send_webhook({
            "run_id": self.run_id,
            "ticker": company_name,
            "date": trade_date,
            "node": "Initializing...",
            "status": "in_progress",
            "timestamp": start_time_iso,
            "start_time": start_time_iso,
            "timing": {
                "total_runtime_seconds": 0.0,
                "node_timings": {},
            },
        })

        # Initialize state — inject memory log context for PM.
        past_context = self.memory_log.get_past_context(company_name)
        init_agent_state = self.propagator.create_initial_state(
            company_name, trade_date, past_context=past_context
        )
        self._send_webhook({
            "run_id": self.run_id,
            "ticker": company_name,
            "date": trade_date,
            "node": "Launching Analyst Branches...",
            "status": "in_progress",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "start_time": start_time_iso,
        })
        args = self.propagator.get_graph_args()

        # Inject thread_id so same ticker+date resumes, different date starts fresh.
        config = args.get("config", {})
        if self.config.get("checkpoint_enabled"):
            tid = thread_id(company_name, str(trade_date))
            config.setdefault("configurable", {})["thread_id"] = tid
            args["config"] = config

        # Even in non-debug mode, we stream to get progress updates
        trace = []
        previous_chunk_at = perf_start
        
        try:
            async for chunk in self.graph.astream(init_agent_state, **args):
                node_name = list(chunk.keys())[0] if chunk else "unknown"
                node_updates = chunk.get(node_name, {})
                now = datetime.utcnow()
                current_perf = time.perf_counter()
                node_elapsed = max(0.0, current_perf - previous_chunk_at)
                previous_chunk_at = current_perf
                self._record_node_timing(timing, node_name, now, node_elapsed)
                trace.append(chunk)
                self._send_in_progress_webhook(
                    company_name,
                    trade_date,
                    node_name,
                    now,
                    start_time_iso,
                    node_updates,
                    perf_start,
                    timing,
                )
        except Exception as e:
            logger.error("Error during graph execution for %s: %s", company_name, e)
            self._send_webhook({
                "run_id": self.run_id,
                "ticker": company_name,
                "date": trade_date,
                "status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "start_time": start_time_iso,
                "timing": {
                    "total_runtime_seconds": round(time.perf_counter() - perf_start, 3),
                    "node_timings": timing["node_timings"],
                },
            })
            raise e

        # Retrieve the final accumulated state from the graph's own state manager
        # This ensures reducers (like add_messages) are correctly applied.
        final_state = await self._aget_graph_state_values(config)

        # Store current state for reflection.
        self.curr_state = final_state
        end_time = datetime.utcnow()
        end_time_iso = end_time.isoformat() + "Z"
        timing["total_runtime_seconds"] = round(time.perf_counter() - perf_start, 3)
        self.run_timing = timing

        # Log state to disk.
        self._log_state(trade_date, final_state, start_time, end_time, timing)

        # Notify completion
        self._send_webhook({
            "run_id": self.run_id,
            "ticker": company_name,
            "date": trade_date,
            "status": "completed",
            "timestamp": end_time_iso,
            "start_time": start_time_iso,
            "end_time": end_time_iso,
            "timing": timing,
        })

        # Store decision for deferred reflection on the next same-ticker run.
        # Skip if standalone (no decision generated).
        final_decision = final_state.get("final_trade_decision")
        if final_decision:
            self.memory_log.store_decision(
                ticker=company_name,
                trade_date=trade_date,
                final_trade_decision=final_decision,
            )

        # Clear checkpoint on successful completion to avoid stale state.
        if self.config.get("checkpoint_enabled"):
            clear_checkpoint(
                self.config["data_cache_dir"], company_name, str(trade_date)
            )

        return final_state, self.process_signal(final_decision) if final_decision else "N/A"

    async def _aget_graph_state_values(self, config):
        """Retrieve graph state values from async or sync state helpers."""
        if hasattr(self.graph, "aget_state"):
            state = await self.graph.aget_state(config)
            return state.values
        state = await asyncio.to_thread(self.graph.get_state, config)
        return state.values

    def _log_state(self, trade_date, final_state, start_time=None, end_time=None, timing=None):
        """Log the final state to a JSON file."""
        invest_debate = final_state.get("investment_debate_state", {})
        risk_debate = final_state.get("risk_debate_state", {})
        
        self.log_states_dict[str(trade_date)] = {
            "company_of_interest": final_state.get("company_of_interest"),
            "trade_date": final_state.get("trade_date"),
            "start_time": start_time.isoformat() if start_time else None,
            "end_time": end_time.isoformat() if end_time else None,
            "market_report": final_state.get("market_report", ""),
            "sentiment_report": final_state.get("sentiment_report", ""),
            "news_report": final_state.get("news_report", ""),
            "fundamentals_report": final_state.get("fundamentals_report", ""),
            "investment_debate_state": {
                "bull_history": invest_debate.get("bull_history", ""),
                "bear_history": invest_debate.get("bear_history", ""),
                "history": invest_debate.get("history", ""),
                "current_response": invest_debate.get("current_response", ""),
                "judge_decision": invest_debate.get("judge_decision", ""),
            },
            "trader_investment_decision": final_state.get("trader_investment_plan", ""),
            "risk_debate_state": {
                "aggressive_history": risk_debate.get("aggressive_history", ""),
                "conservative_history": risk_debate.get("conservative_history", ""),
                "neutral_history": risk_debate.get("neutral_history", ""),
                "history": risk_debate.get("history", ""),
                "judge_decision": risk_debate.get("judge_decision", ""),
            },
            "investment_plan": final_state.get("investment_plan", ""),
            "final_trade_decision": final_state.get("final_trade_decision", ""),
            "timing": timing or {},
        }

        # Save to file. Reject ticker values that would escape the
        # results directory when joined as a path component.
        safe_ticker = safe_ticker_component(self.ticker)
        directory = Path(self.config["results_dir"]) / safe_ticker / "TradingAgentsStrategy_logs"
        directory.mkdir(parents=True, exist_ok=True)

        log_path = directory / f"full_states_log_{trade_date}.json"
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(self.log_states_dict[str(trade_date)], f, indent=4)

    def process_signal(self, full_signal):
        """Process a signal to extract the core decision."""
        return self.signal_processor.process_signal(full_signal)

    def _send_webhook(self, data: Dict[str, Any]):
        """Send a progress update to the configured webhook URL."""
        self.webhook_dispatcher.enqueue(data)
