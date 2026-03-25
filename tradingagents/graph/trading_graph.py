# TradingAgents/graph/trading_graph.py

import os
from copy import deepcopy
import json
from pathlib import Path
from typing import Dict, Any, List, Optional

from langgraph.prebuilt import ToolNode

from tradingagents.llm_clients import create_llm_client

from tradingagents.agents import *
from tradingagents.default_config import DEFAULT_CONFIG, normalize_llm_routing
from tradingagents.agents.utils.memory import FinancialSituationMemory
from tradingagents.agents.utils.agent_states import (
    AgentState,
    InvestDebateState,
    RiskDebateState,
)
from tradingagents.dataflows.config import set_config

# Import the new abstract tool methods from agent_utils
from tradingagents.agents.utils.agent_utils import (
    build_social_tools,
    get_stock_data,
    get_indicators,
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement,
    get_economic_indicators,
    get_fed_calendar,
    get_news,
    get_insider_transactions,
    get_global_news,
    get_catalyst_calendar,
    get_scenario_fundamentals,
    get_scenario_news,
    get_segment_fundamentals,
    get_segment_income_statement,
    get_segment_news,
    get_sizing_fundamentals,
    get_sizing_indicator,
    get_sizing_price_history,
    has_social_sentiment_support,
    get_valuation_inputs,
    get_yield_curve,
)

from .conditional_logic import ConditionalLogic
from .setup import GraphSetup
from .propagation import Propagator
from .reflection import Reflector
from .signal_processing import SignalProcessor


class TradingAgentsGraph:
    """Main class that orchestrates the trading agents framework."""

    ALWAYS_ON_ROLES = {
        "bull_researcher",
        "bear_researcher",
        "research_manager",
        "trader",
        "aggressive_analyst",
        "neutral_analyst",
        "conservative_analyst",
        "portfolio_manager",
    }
    QUICK_THINKING_ROLES = {
        "market",
        "social",
        "news",
        "fundamentals",
        "factor_rules",
        "valuation",
        "segment",
        "scenario",
        "position_sizing",
        "macro",
        "bull_researcher",
        "bear_researcher",
        "trader",
        "aggressive_analyst",
        "neutral_analyst",
        "conservative_analyst",
    }
    DEEP_THINKING_ROLES = {
        "research_manager",
        "portfolio_manager",
    }

    def __init__(
        self,
        selected_analysts=["market", "social", "news", "fundamentals", "macro"],
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
        self.config = self._build_config(config)
        self.callbacks = callbacks or []

        # Update the interface's config
        set_config(self.config)

        # Create necessary directories
        os.makedirs(
            os.path.join(self.config["project_dir"], "dataflows/data_cache"),
            exist_ok=True,
        )

        self.quick_thinking_llm = self._create_legacy_llm("quick")
        self.deep_thinking_llm = self._create_legacy_llm("deep")
        self.role_llms = self._create_role_llms(selected_analysts)
        self.social_sentiment_available = has_social_sentiment_support()
        
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
            role_llms=self.role_llms,
            social_sentiment_available=self.social_sentiment_available,
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

    def _build_config(self, config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Merge user config over defaults without mutating the shared defaults."""
        return normalize_llm_routing(self._deep_merge_dicts(DEFAULT_CONFIG, config or {}))

    def _normalize_provider(self, provider: Optional[str]) -> str:
        return (provider or "").lower()

    def _deep_merge_dicts(
        self,
        base: Dict[str, Any],
        override: Dict[str, Any],
    ) -> Dict[str, Any]:
        merged = deepcopy(base)
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = self._deep_merge_dicts(merged[key], value)
            else:
                merged[key] = deepcopy(value)
        return merged

    def _create_legacy_llm(self, thinker_depth: str):
        model_key = "deep_think_llm" if thinker_depth == "deep" else "quick_think_llm"
        provider = self._normalize_provider(self.config["llm_provider"])
        llm_kwargs = self._get_provider_kwargs(provider)
        if self.callbacks:
            llm_kwargs["callbacks"] = self.callbacks

        client = create_llm_client(
            provider=provider,
            model=self.config[model_key],
            base_url=self.config.get("backend_url"),
            **llm_kwargs,
        )
        return client.get_llm()

    def _create_role_llms(self, selected_analysts: List[str]) -> Dict[str, Any]:
        role_llms = {}
        llm_cache = {}
        for role in self._get_required_roles(selected_analysts):
            thinker_depth = "deep" if role in self.DEEP_THINKING_ROLES else "quick"
            llm_config = self._resolve_llm_config(role, thinker_depth)
            if self._uses_legacy_llm(llm_config, thinker_depth):
                continue
            cache_key = (
                llm_config["provider"],
                llm_config["model"],
                llm_config.get("base_url"),
            )
            if cache_key not in llm_cache:
                llm_cache[cache_key] = self._create_llm_from_config(llm_config)
            role_llms[role] = llm_cache[cache_key]
        return role_llms

    def _get_required_roles(self, selected_analysts: List[str]) -> set[str]:
        return self.ALWAYS_ON_ROLES | set(selected_analysts)

    def _create_llm_from_config(self, llm_config: Dict[str, Any]):
        llm_kwargs = self._get_provider_kwargs(llm_config["provider"])
        if self.callbacks:
            llm_kwargs["callbacks"] = self.callbacks

        client = create_llm_client(
            provider=llm_config["provider"],
            model=llm_config["model"],
            base_url=llm_config.get("base_url"),
            **llm_kwargs,
        )
        return client.get_llm()

    def _uses_legacy_llm(self, llm_config: Dict[str, Any], thinker_depth: str) -> bool:
        model_key = "deep_think_llm" if thinker_depth == "deep" else "quick_think_llm"
        return (
            llm_config["provider"] == self._normalize_provider(self.config["llm_provider"])
            and llm_config["model"] == self.config[model_key]
            and llm_config.get("base_url") == self.config.get("backend_url")
        )

    def _resolve_llm_config(
        self,
        role: str,
        thinker_depth: str,
    ) -> Dict[str, Any]:
        routing = self.config.get("llm_routing") or {}
        role_routes = routing.get("roles") or {}
        model_key = "deep_think_llm" if thinker_depth == "deep" else "quick_think_llm"
        legacy_provider = self._normalize_provider(self.config["llm_provider"])
        legacy_route = {
            "provider": legacy_provider,
            "model": self.config[model_key],
            "base_url": self.config.get("backend_url"),
        }
        default_route = routing.get("default") or {}
        role_route = role_routes.get(role) or {}
        route = self._deep_merge_dicts(legacy_route, default_route)
        route = self._deep_merge_dicts(route, role_route)
        route["provider"] = self._normalize_provider(route.get("provider"))
        explicit_routed_base_url = "base_url" in default_route or "base_url" in role_route
        if route["provider"] != legacy_provider and not explicit_routed_base_url:
            route["base_url"] = None
        return route

    def _get_provider_kwargs(self, provider: Optional[str] = None) -> Dict[str, Any]:
        """Get provider-specific kwargs for LLM client creation."""
        kwargs = {}
        provider = (provider or self.config.get("llm_provider", "")).lower()

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
        social_tools = build_social_tools(
            getattr(self, "social_sentiment_available", has_social_sentiment_support())
        )
        return {
            "market": ToolNode(
                [
                    # Core stock data tools
                    get_stock_data,
                    # Technical indicators
                    get_indicators,
                ]
            ),
            "social": ToolNode(social_tools),
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
            "valuation": ToolNode(
                [
                    # Valuation analysis tools
                    get_valuation_inputs,
                ]
            ),
            "segment": ToolNode(
                [
                    # Segment and business-mix analysis tools
                    get_segment_fundamentals,
                    get_segment_income_statement,
                    get_segment_news,
                ]
            ),
            "scenario": ToolNode(
                [
                    # Scenario and catalyst mapping tools
                    get_scenario_fundamentals,
                    get_scenario_news,
                    get_catalyst_calendar,
                ]
            ),
            "position_sizing": ToolNode(
                [
                    # Position sizing analysis tools
                    get_sizing_fundamentals,
                    get_sizing_indicator,
                    get_sizing_price_history,
                ]
            ),
            "macro": ToolNode(
                [
                    # Macroeconomic analysis tools
                    get_economic_indicators,
                    get_yield_curve,
                    get_fed_calendar,
                ]
            ),
        }

    def propagate(self, company_name, trade_date):
        """Run the trading agents graph for a company on a specific date."""

        self.ticker = company_name

        # Initialize state
        init_agent_state = self.propagator.create_initial_state(
            company_name, trade_date
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

        # Store current state for reflection
        self.curr_state = final_state

        # Log state
        self._log_state(trade_date, final_state)

        # Return decision and processed signal
        return final_state, self.process_signal(final_state["final_trade_decision"])

    def _log_state(self, trade_date, final_state):
        """Log the final state to a JSON file."""
        self.log_states_dict[str(trade_date)] = {
            "company_of_interest": final_state["company_of_interest"],
            "trade_date": final_state["trade_date"],
            "market_report": final_state["market_report"],
            "sentiment_report": final_state["sentiment_report"],
            "news_report": final_state["news_report"],
            "fundamentals_report": final_state["fundamentals_report"],
            "factor_rules_report": final_state.get("factor_rules_report", ""),
            "segment_report": final_state.get("segment_report", ""),
            "segment_data": final_state.get("segment_data", {}),
            "macro_report": final_state.get("macro_report", ""),
            "scenario_catalyst_report": final_state.get("scenario_catalyst_report", ""),
            "scenario_catalyst_data": final_state.get("scenario_catalyst_data", {}),
            "position_sizing_report": final_state.get("position_sizing_report", ""),
            "position_sizing_data": final_state.get("position_sizing_data", {}),
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
        self.reflector.reflect_portfolio_manager(
            self.curr_state, returns_losses, self.portfolio_manager_memory
        )

    def process_signal(self, full_signal):
        """Process a signal to extract the core decision."""
        return self.signal_processor.process_signal(full_signal)
