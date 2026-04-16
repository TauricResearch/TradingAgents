# TradingAgents/graph/trading_graph.py

import copy
import os
from pathlib import Path
import json
from datetime import date
from typing import Dict, Any, Tuple, List, Optional

from langgraph.prebuilt import ToolNode

from tradingagents.llm_clients import create_llm_client

from tradingagents.agents import *
from tradingagents.default_config import get_default_config
from tradingagents.agents.utils.memory import FinancialSituationMemory
from tradingagents.agents.utils.agent_states import (
    AgentState,
    InvestDebateState,
    RiskDebateState,
    extract_research_provenance,
)
from tradingagents.agents.utils.decision_utils import build_structured_decision
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


def _merge_with_default_config(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge a partial user config onto the runtime default config.

    Orchestrator callers often override only a few LLM/vendor fields. Without a
    merge step, required defaults such as ``project_dir`` disappear and the
    graph fails during initialization.
    """
    merged = get_default_config()
    if not config:
        return merged

    for key, value in config.items():
        if (
            key in ("data_vendors", "tool_vendors")
            and isinstance(value, dict)
            and isinstance(merged.get(key), dict)
        ):
            merged[key].update(value)
        else:
            merged[key] = value

    return merged


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
        self.config = _merge_with_default_config(config)
        self.callbacks = callbacks or []

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
        self.portfolio_manager_memory = FinancialSituationMemory("portfolio_manager_memory", self.config)

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
            self.portfolio_manager_memory,
            self.conditional_logic,
            analyst_node_timeout_secs=float(self.config.get("analyst_node_timeout_secs", 75.0)),
            research_node_timeout_secs=float(self.config.get("research_node_timeout_secs", 30.0)),
        )

        self.propagator = Propagator()
        self.reflector = Reflector(self.quick_thinking_llm)
        self.signal_processor = SignalProcessor(self.quick_thinking_llm)

        # State tracking
        self.curr_state = None
        self.ticker = None
        self.log_states_dict = {}  # date to full state dict

        # Set up the graph
        self.graph = self.graph_setup.setup_graph(selected_analysts)

    def _get_provider_kwargs(self) -> Dict[str, Any]:
        """Get provider-specific kwargs for LLM client creation."""
        kwargs = {}
        provider = self.config.get("llm_provider", "").lower()

        common_passthrough = {
            "timeout": ("llm_timeout", "timeout"),
            "max_retries": ("llm_max_retries", "max_retries"),
        }
        for out_key, config_keys in common_passthrough.items():
            for config_key in config_keys:
                value = self.config.get(config_key)
                if value is not None:
                    kwargs[out_key] = value
                    break

        if provider == "google":
            thinking_level = self.config.get("google_thinking_level")
            if thinking_level:
                kwargs["thinking_level"] = thinking_level

        elif provider == "openai":
            reasoning_effort = self.config.get("openai_reasoning_effort")
            if reasoning_effort:
                kwargs["reasoning_effort"] = reasoning_effort
            # Allow disabling Responses API for third-party OpenAI-compatible providers
            if "use_responses_api" in self.config:
                kwargs["use_responses_api"] = self.config["use_responses_api"]

        elif provider == "anthropic":
            effort = self.config.get("anthropic_effort")
            if effort:
                kwargs["effort"] = effort

        # Pass api_key if present in config (for MiniMax and other third-party Anthropic-compatible APIs)
        api_key = self.config.get("api_key")
        if api_key:
            kwargs["api_key"] = api_key

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

    def propagate(self, company_name, trade_date):
        """Run the trading agents graph for a company on a specific date."""

        self.ticker = company_name

        # Initialize state
        init_agent_state = self.propagator.create_initial_state(
            company_name,
            trade_date,
            portfolio_context=str(self.config.get("portfolio_context", "") or ""),
            peer_context=str(self.config.get("peer_context", "") or ""),
            peer_context_mode=str(self.config.get("peer_context_mode", "UNSPECIFIED") or "UNSPECIFIED"),
        )
        args = self.propagator.get_graph_args()

        if self.debug:
            # Debug mode with tracing
            trace = []
            for chunk in self.graph.stream(init_agent_state, **args):
                if len(chunk["messages"]) == 0:
                    pass
                else:
                    chunk["messages"][-1].pretty_print()
                    trace.append(chunk)

            final_state = trace[-1]
        else:
            # Standard mode without tracing
            final_state = self.graph.invoke(init_agent_state, **args)

        final_state = self._normalize_decision_outputs(final_state)

        # Store current state for reflection
        self.curr_state = final_state

        # Log state
        self._log_state(trade_date, final_state)

        # Return decision and processed signal
        return final_state, self.process_signal(final_state["final_trade_decision"])

    def _normalize_decision_outputs(self, final_state: Dict[str, Any]) -> Dict[str, Any]:
        normalized = copy.deepcopy(final_state)
        portfolio_context = bool(str(normalized.get("portfolio_context", "") or "").strip())
        peer_context = bool(str(normalized.get("peer_context", "") or "").strip())
        context_usage = {
            "portfolio_context": portfolio_context,
            "peer_context": peer_context,
        }

        investment_plan = str(normalized.get("investment_plan", "") or "")
        trader_plan = str(normalized.get("trader_investment_plan", "") or "")
        final_rating = str(normalized.get("final_trade_decision", "") or "")
        final_report = str(
            normalized.get("final_trade_decision_report")
            or normalized.get("risk_debate_state", {}).get("judge_decision", "")
            or final_rating
        )

        investment_structured = normalized.get("investment_plan_structured") or build_structured_decision(
            investment_plan,
            default_rating="HOLD",
            peer_context_mode=normalized.get("peer_context_mode", "UNSPECIFIED"),
            context_usage=context_usage,
        )
        trader_structured = normalized.get("trader_investment_plan_structured") or build_structured_decision(
            trader_plan,
            fallback_candidates=(("investment_plan", investment_plan),),
            default_rating="HOLD",
            peer_context_mode=normalized.get("peer_context_mode", "UNSPECIFIED"),
            context_usage=context_usage,
        )
        final_structured = normalized.get("final_trade_decision_structured") or build_structured_decision(
            final_report,
            fallback_candidates=(
                ("trader_plan", trader_plan),
                ("investment_plan", investment_plan),
            ),
            default_rating="HOLD",
            peer_context_mode=normalized.get("peer_context_mode", "UNSPECIFIED"),
            context_usage=context_usage,
        )

        if final_rating and final_rating != final_structured["rating"]:
            warnings = list(final_structured.get("warnings") or [])
            warnings.append(f"final_trade_decision_overridden:{final_rating}->{final_structured['rating']}")
            final_structured["warnings"] = warnings

        normalized["investment_plan_structured"] = investment_structured
        normalized["trader_investment_plan_structured"] = trader_structured
        normalized["final_trade_decision"] = final_structured["rating"]
        normalized["final_trade_decision_report"] = final_structured["report_text"]
        normalized["final_trade_decision_structured"] = final_structured

        risk_state = dict(normalized.get("risk_debate_state") or {})
        risk_state["judge_decision"] = final_structured["report_text"]
        normalized["risk_debate_state"] = risk_state

        return normalized

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
                **(
                    extract_research_provenance(
                        final_state.get("investment_debate_state")
                    )
                    or {}
                ),
            },
            "trader_investment_decision": final_state["trader_investment_plan"],
            "trader_investment_plan_structured": final_state.get("trader_investment_plan_structured", {}),
            "risk_debate_state": {
                "aggressive_history": final_state["risk_debate_state"]["aggressive_history"],
                "conservative_history": final_state["risk_debate_state"]["conservative_history"],
                "neutral_history": final_state["risk_debate_state"]["neutral_history"],
                "history": final_state["risk_debate_state"]["history"],
                "judge_decision": final_state["risk_debate_state"]["judge_decision"],
            },
            "investment_plan": final_state["investment_plan"],
            "investment_plan_structured": final_state.get("investment_plan_structured", {}),
            "final_trade_decision": final_state["final_trade_decision"],
            "final_trade_decision_report": final_state.get("final_trade_decision_report", ""),
            "final_trade_decision_structured": final_state.get("final_trade_decision_structured", {}),
        }

        # Save to file
        directory = Path(self.config["results_dir"]) / self.ticker / "TradingAgentsStrategy_logs"
        directory.mkdir(parents=True, exist_ok=True)

        log_path = directory / f"full_states_log_{trade_date}.json"
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(self.log_states_dict[str(trade_date)], f, indent=4)

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
        self.reflector.reflect_portfolio_manager(
            self.curr_state, returns_losses, self.portfolio_manager_memory
        )

    def process_signal(self, full_signal):
        """Process a signal to extract the core decision."""
        return self.signal_processor.process_signal(full_signal)
