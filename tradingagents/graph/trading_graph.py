# TradingAgents/graph/trading_graph.py

import os
import sqlite3
import hashlib
import logging
from pathlib import Path
import json
from datetime import date
from typing import Dict, Any, Tuple, List, Optional

logger = logging.getLogger(__name__)

from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.sqlite import SqliteSaver

from tradingagents.llm_clients import create_llm_client

from tradingagents.agents import *
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.agents.utils.memory import FinancialSituationMemory
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

from .conditional_logic import ConditionalLogic
from .setup import GraphSetup
from .propagation import Propagator
from .reflection import Reflector
from .signal_processing import SignalProcessor


_NODE_TO_STEP = {
    "Market Analyst":       "market_analyst",
    "News Analyst":         "news_analyst",
    "Fundamentals Analyst": "fundamentals_analyst",
    "Social Analyst":       "social_analyst",
    "Bull Researcher":      "bull_researcher",
    "Bear Researcher":      "bear_researcher",
    "Research Manager":     "research_manager",
    "Trader":               "trader",
    "Aggressive Analyst":   "aggressive_analyst",
    "Conservative Analyst": "conservative_analyst",
    "Neutral Analyst":      "neutral_analyst",
    "Risk Judge":           "risk_judge",
    "Chief Analyst":        "chief_analyst",
}

_SKIP_NODES = {"tools_market", "tools_news", "tools_fundamentals", "tools_social"}


class TradingAgentsGraph:
    """Main class that orchestrates the trading agents framework."""

    def __init__(
        self,
        selected_analysts=["market", "social", "news", "fundamentals"],
        debug=False,
        config: Dict[str, Any] = None,
        callbacks: Optional[List] = None,
    ):
        """Initialize the trading agents graph and components.

        Args:
            selected_analysts: List of analyst types to include
            debug: Whether to run in debug mode
            config: Configuration dictionary. If None, uses default config
            callbacks: Optional list of callback handlers (e.g., for tracking LLM/tool stats)
        """
        self.debug = debug
        self.config = config or DEFAULT_CONFIG
        self.callbacks = callbacks or []
        self.selected_analysts = list(selected_analysts)

        # Update the interface's config
        set_config(self.config)

        # Create necessary directories
        os.makedirs(
            os.path.join(self.config["project_dir"], "dataflows/data_cache"),
            exist_ok=True,
        )

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
        
        # Initialize memories
        self.bull_memory = FinancialSituationMemory("bull_memory", self.config)
        self.bear_memory = FinancialSituationMemory("bear_memory", self.config)
        self.trader_memory = FinancialSituationMemory("trader_memory", self.config)
        self.invest_judge_memory = FinancialSituationMemory("invest_judge_memory", self.config)
        self.risk_manager_memory = FinancialSituationMemory("risk_manager_memory", self.config)

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
            self.bull_memory,
            self.bear_memory,
            self.trader_memory,
            self.invest_judge_memory,
            self.risk_manager_memory,
            self.conditional_logic,
        )

        self.propagator = Propagator()
        self.reflector = Reflector(self.quick_thinking_llm)
        self.signal_processor = SignalProcessor(self.quick_thinking_llm)

        # State tracking
        self.curr_state = None
        self.ticker = None
        self.log_states_dict = {}  # date to full state dict

        self._sqlite_conn, self.checkpointer = self._create_sqlite_checkpointer(self.config)
        # Set up the graph (durable checkpoints for resume after crash)
        self.graph = self.graph_setup.setup_graph(
            selected_analysts, checkpointer=self.checkpointer
        )

    @staticmethod
    def _create_sqlite_checkpointer(
        config: Dict[str, Any],
    ) -> Tuple[sqlite3.Connection, SqliteSaver]:
        """SQLite checkpoint store under results_dir/.checkpoints/langgraph.sqlite.

        Returns:
            (conn, checkpointer) – caller must close conn when done.
        """
        results_dir = Path(config.get("results_dir", "./results")).expanduser().resolve()
        checkpoint_dir = results_dir / ".checkpoints"
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        db_path = checkpoint_dir / "langgraph.sqlite"
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        return conn, SqliteSaver(conn)

    def close(self) -> None:
        """Close the underlying SQLite connection held by the checkpointer."""
        try:
            self._sqlite_conn.close()
        except Exception:
            pass

    def __del__(self) -> None:
        self.close()

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
                ]
            ),
            "social": ToolNode(
                [
                    # News tools for social media analysis
                    get_news,
                ]
            ),
            "news": ToolNode(
                [
                    # News and insider information
                    get_news,
                    get_global_news,
                    get_insider_transactions,
                ]
            ),
            "fundamentals": ToolNode(
                [
                    # Fundamental analysis tools
                    get_fundamentals,
                    get_balance_sheet,
                    get_cashflow,
                    get_income_statement,
                ]
            ),
        }

    def propagate(self, company_name, trade_date, thread_id: Optional[str] = None):
        """Run the trading agents graph for a company on a specific date."""

        self.ticker = company_name

        if thread_id is None:
            payload = json.dumps(
                {
                    "ticker": company_name.strip().upper(),
                    "trade_date": str(trade_date),
                    "analysts": sorted(self.selected_analysts),
                    "llm_provider": self.config.get("llm_provider"),
                    "deep_think_llm": self.config.get("deep_think_llm"),
                    "quick_think_llm": self.config.get("quick_think_llm"),
                    "max_debate_rounds": self.config.get("max_debate_rounds"),
                    "max_risk_discuss_rounds": self.config.get("max_risk_discuss_rounds"),
                },
                sort_keys=True,
            ).encode()
            thread_id = "ta_prog_" + hashlib.sha256(payload).hexdigest()[:24]

        # Initialize state
        init_agent_state = self.propagator.create_initial_state(
            company_name, trade_date
        )
        args = self.propagator.get_graph_args(thread_id=thread_id)

        # Determine stream input: resume from checkpoint if an incomplete run exists,
        # otherwise start fresh. Passing None tells LangGraph to resume from the last
        # saved checkpoint for this thread_id.
        thread_config = {"configurable": {"thread_id": thread_id}}
        snap = self.graph.get_state(thread_config)
        if snap.next:
            # Incomplete run found — resume automatically (no user prompt in API mode)
            stream_input = None
        else:
            stream_input = init_agent_state

        if self.debug:
            # Debug mode with tracing
            trace = []
            for chunk in self.graph.stream(stream_input, **args):
                if len(chunk["messages"]) == 0:
                    pass
                else:
                    chunk["messages"][-1].pretty_print()
                    trace.append(chunk)

            if not trace:
                raise RuntimeError(
                    "Graph stream produced no output — all chunks had empty messages. "
                    f"ticker={company_name}, trade_date={trade_date}, thread_id={thread_id}"
                )
            final_state = trace[-1]
        else:
            # Standard mode without tracing
            final_state = self.graph.invoke(stream_input, **args)

        # Store current state for reflection
        self.curr_state = final_state

        # Log state
        self._log_state(trade_date, final_state)

        # Return decision and processed signal (prefer structured chief_analyst_report verdict)
        chief_report = (final_state.get("chief_analyst_report") or {})
        if chief_report.get("verdict") in {"BUY", "SELL", "HOLD"}:
            decision = chief_report["verdict"]
        else:
            decision = self.process_signal(final_state.get("final_trade_decision", ""))
        return final_state, decision

    @staticmethod
    def _extract_report(step_key: str, update: dict) -> str:
        """Extract the relevant report string from a node's state update."""
        extractors = {
            "market_analyst":       lambda u: u.get("market_report", ""),
            "news_analyst":         lambda u: u.get("news_report", ""),
            "fundamentals_analyst": lambda u: u.get("fundamentals_report", ""),
            "social_analyst":       lambda u: u.get("sentiment_report", ""),
            "bull_researcher":      lambda u: (u.get("investment_debate_state") or {}).get("bull_history", ""),
            "bear_researcher":      lambda u: (u.get("investment_debate_state") or {}).get("bear_history", ""),
            "research_manager":     lambda u: u.get("investment_plan", ""),
            "trader":               lambda u: u.get("trader_investment_plan", ""),
            "aggressive_analyst":   lambda u: (u.get("risk_debate_state") or {}).get("current_aggressive_response", ""),
            "conservative_analyst": lambda u: (u.get("risk_debate_state") or {}).get("current_conservative_response", ""),
            "neutral_analyst":      lambda u: (u.get("risk_debate_state") or {}).get("current_neutral_response", ""),
            "risk_judge":           lambda u: (u.get("risk_debate_state") or {}).get("judge_decision", ""),
            "chief_analyst":        lambda u: json.dumps(u.get("chief_analyst_report") or {}),
        }
        return extractors[step_key](update) or ""

    def stream_propagate(self, company_name: str, trade_date: str, thread_id=None):
        """Stream trading analysis events as each agent node completes.

        Yields:
            (step_key, report) tuples for each meaningful node completion.

        After the generator is exhausted, self._last_decision is set to the
        normalized decision string ("BUY", "SELL", or "HOLD").
        """
        self.ticker = company_name
        self._last_decision = None

        if thread_id is None:
            payload = json.dumps(
                {
                    "ticker": company_name.strip().upper(),
                    "trade_date": str(trade_date),
                    "analysts": sorted(self.selected_analysts),
                    "llm_provider": self.config.get("llm_provider"),
                    "deep_think_llm": self.config.get("deep_think_llm"),
                    "quick_think_llm": self.config.get("quick_think_llm"),
                    "max_debate_rounds": self.config.get("max_debate_rounds"),
                    "max_risk_discuss_rounds": self.config.get("max_risk_discuss_rounds"),
                },
                sort_keys=True,
            ).encode()
            thread_id = "ta_prog_" + hashlib.sha256(payload).hexdigest()[:24]

        init_agent_state = self.propagator.create_initial_state(company_name, trade_date)
        args = self.propagator.get_graph_args(thread_id=thread_id)
        args["stream_mode"] = "updates"  # stream per-node deltas, not full state snapshots

        thread_config = {"configurable": {"thread_id": thread_id}}
        snap = self.graph.get_state(thread_config)
        stream_input = None if snap.next else init_agent_state

        for chunk in self.graph.stream(stream_input, **args):
            node_name, update = next(iter(chunk.items()))

            # Filter: skip list first, then known nodes, else warn and skip
            if node_name in _SKIP_NODES or node_name.startswith("Msg Clear"):
                continue
            if node_name not in _NODE_TO_STEP:
                logger.warning("stream_propagate: unknown node '%s' — skipping", node_name)
                continue

            step_key = _NODE_TO_STEP[node_name]
            report = TradingAgentsGraph._extract_report(step_key, update)

            yield step_key, report

        # Post-loop: fetch the complete final state snapshot (all fields populated).
        # stream_mode="updates" gives only deltas — use get_state() for the full picture
        # needed by _log_state and process_signal.
        final_snap = self.graph.get_state(thread_config)
        final_state = final_snap.values if hasattr(final_snap, "values") else {}

        chief_report = final_state.get("chief_analyst_report") or {}
        if chief_report.get("verdict") in {"BUY", "SELL", "HOLD"}:
            decision = chief_report["verdict"]
        else:
            # Fallback for partial runs or old checkpoints without chief_analyst_report
            try:
                raw_signal = final_state.get("final_trade_decision", "")
                raw_decision = self.process_signal(raw_signal)
                decision = raw_decision.strip().upper()
                if decision not in {"BUY", "SELL", "HOLD"}:
                    logger.warning("stream_propagate: unexpected decision '%s' — defaulting to HOLD", decision)
                    decision = "HOLD"
            except Exception:
                raise  # propagate to run_service for run:error handling

        self._last_decision = decision
        self._log_state(trade_date, final_state)

    def _log_state(self, trade_date, final_state):
        """Log the final state to a JSON file."""
        self.log_states_dict[str(trade_date)] = {
            "company_of_interest": final_state["company_of_interest"],
            "trade_date": final_state["trade_date"],
            "market_report": final_state["market_report"],
            "sentiment_report": final_state["sentiment_report"],
            "news_report": final_state["news_report"],
            "fundamentals_report": final_state["fundamentals_report"],
            "investment_debate_state": {
                "bull_history": final_state["investment_debate_state"]["bull_history"],
                "bear_history": final_state["investment_debate_state"]["bear_history"],
                "history": final_state["investment_debate_state"]["history"],
                "current_response": final_state["investment_debate_state"][
                    "current_response"
                ],
                "judge_decision": final_state["investment_debate_state"][
                    "judge_decision"
                ],
            },
            "trader_investment_decision": final_state["trader_investment_plan"],
            "risk_debate_state": {
                "aggressive_history": final_state["risk_debate_state"]["aggressive_history"],
                "conservative_history": final_state["risk_debate_state"]["conservative_history"],
                "neutral_history": final_state["risk_debate_state"]["neutral_history"],
                "history": final_state["risk_debate_state"]["history"],
                "judge_decision": final_state["risk_debate_state"]["judge_decision"],
            },
            "investment_plan": final_state["investment_plan"],
            "final_trade_decision": final_state["final_trade_decision"],
            "chief_analyst_report": final_state.get("chief_analyst_report"),
        }

        # Save to file
        directory = Path(f"eval_results/{self.ticker}/TradingAgentsStrategy_logs/")
        directory.mkdir(parents=True, exist_ok=True)

        with open(
            f"eval_results/{self.ticker}/TradingAgentsStrategy_logs/full_states_log_{trade_date}.json",
            "w",
            encoding="utf-8",
        ) as f:
            json.dump(self.log_states_dict, f, indent=4)

    def reflect_and_remember(self, returns_losses):
        """Reflect on decisions and update memory based on returns."""
        self.reflector.reflect_bull_researcher(
            self.curr_state, returns_losses, self.bull_memory
        )
        self.reflector.reflect_bear_researcher(
            self.curr_state, returns_losses, self.bear_memory
        )
        self.reflector.reflect_trader(
            self.curr_state, returns_losses, self.trader_memory
        )
        self.reflector.reflect_invest_judge(
            self.curr_state, returns_losses, self.invest_judge_memory
        )
        self.reflector.reflect_risk_manager(
            self.curr_state, returns_losses, self.risk_manager_memory
        )

    def process_signal(self, full_signal):
        """Process a signal to extract the core decision."""
        return self.signal_processor.process_signal(full_signal)
