# TradingAgents/prediction_market/graph/pm_trading_graph.py

import os
from pathlib import Path
import json
from datetime import date
from typing import Dict, Any, Tuple, List, Optional

from langgraph.prebuilt import ToolNode

from tradingagents.llm_clients import create_llm_client

from tradingagents.prediction_market.agents import *
from tradingagents.prediction_market.pm_config import PM_DEFAULT_CONFIG
from tradingagents.agents.utils.memory import FinancialSituationMemory
from tradingagents.prediction_market.agents.utils.pm_agent_states import (
    PMAgentState,
    PMInvestDebateState,
    PMRiskDebateState,
)

# Import PM tool functions
from tradingagents.prediction_market.agents.utils.pm_agent_utils import (
    get_market_info,
    get_market_price_history,
    get_order_book,
    get_resolution_criteria,
    get_event_context,
    get_related_markets,
    search_markets,
    get_news,
    get_global_news,
)

from .conditional_logic import PMConditionalLogic
from .setup import PMGraphSetup
from .propagation import PMPropagator
from .reflection import PMReflector
from .signal_processing import PMSignalProcessor


class PMTradingAgentsGraph:
    """Main class that orchestrates the prediction market trading agents framework."""

    def __init__(
        self,
        selected_analysts=["event", "odds", "information", "sentiment"],
        debug=False,
        config: Dict[str, Any] = None,
        callbacks: Optional[List] = None,
    ):
        """Initialize the prediction market trading agents graph and components.

        Args:
            selected_analysts: List of analyst types to include
            debug: Whether to run in debug mode
            config: Configuration dictionary. If None, uses PM default config
            callbacks: Optional list of callback handlers (e.g., for tracking LLM/tool stats)
        """
        self.debug = debug
        self.config = config or PM_DEFAULT_CONFIG
        self.callbacks = callbacks or []

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
        self.yes_memory = FinancialSituationMemory("yes_memory", self.config)
        self.no_memory = FinancialSituationMemory("no_memory", self.config)
        self.trader_memory = FinancialSituationMemory("trader_memory", self.config)
        self.invest_judge_memory = FinancialSituationMemory("invest_judge_memory", self.config)
        self.risk_manager_memory = FinancialSituationMemory("risk_manager_memory", self.config)

        # Create tool nodes
        self.tool_nodes = self._create_tool_nodes()

        # Initialize components
        self.conditional_logic = PMConditionalLogic(
            max_debate_rounds=self.config["max_debate_rounds"],
            max_risk_discuss_rounds=self.config["max_risk_discuss_rounds"],
        )
        self.graph_setup = PMGraphSetup(
            self.quick_thinking_llm,
            self.deep_thinking_llm,
            self.tool_nodes,
            self.yes_memory,
            self.no_memory,
            self.trader_memory,
            self.invest_judge_memory,
            self.risk_manager_memory,
            self.conditional_logic,
        )

        self.propagator = PMPropagator()
        self.reflector = PMReflector(self.quick_thinking_llm)
        self.signal_processor = PMSignalProcessor(self.quick_thinking_llm)

        # State tracking
        self.curr_state = None
        self.market_id = None
        self.log_states_dict = {}  # date to full state dict

        # Set up the graph
        self.graph = self.graph_setup.setup_graph(selected_analysts)

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
        """Create tool nodes for different prediction market data sources."""
        return {
            "event": ToolNode(
                [
                    # Event context and resolution
                    get_market_info,
                    get_resolution_criteria,
                    get_event_context,
                ]
            ),
            "odds": ToolNode(
                [
                    # Price, order book, and market data
                    get_market_info,
                    get_market_price_history,
                    get_order_book,
                ]
            ),
            "information": ToolNode(
                [
                    # News and related markets
                    get_news,
                    get_global_news,
                    get_related_markets,
                    search_markets,
                ]
            ),
            "sentiment": ToolNode(
                [
                    # News for sentiment analysis
                    get_news,
                    get_global_news,
                ]
            ),
        }

    def propagate(self, market_id, trade_date, market_question=""):
        """Run the prediction market trading agents graph for a market on a specific date.

        Args:
            market_id: The Polymarket condition ID or market identifier
            trade_date: The date of analysis
            market_question: Optional full text of the market question
        """

        self.market_id = market_id

        # Initialize state
        init_agent_state = self.propagator.create_initial_state(
            market_id, trade_date, market_question
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
            "market_id": final_state["market_id"],
            "market_question": final_state["market_question"],
            "trade_date": final_state["trade_date"],
            "event_report": final_state["event_report"],
            "odds_report": final_state["odds_report"],
            "information_report": final_state["information_report"],
            "sentiment_report": final_state["sentiment_report"],
            "investment_debate_state": {
                "yes_history": final_state["investment_debate_state"]["yes_history"],
                "no_history": final_state["investment_debate_state"]["no_history"],
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
        directory = Path(f"eval_results/{self.market_id}/PMTradingAgentsStrategy_logs/")
        directory.mkdir(parents=True, exist_ok=True)

        with open(
            f"eval_results/{self.market_id}/PMTradingAgentsStrategy_logs/full_states_log_{trade_date}.json",
            "w",
            encoding="utf-8",
        ) as f:
            json.dump(self.log_states_dict, f, indent=4)

    def reflect_and_remember(self, returns_losses):
        """Reflect on decisions and update memory based on returns."""
        self.reflector.reflect_yes_researcher(
            self.curr_state, returns_losses, self.yes_memory
        )
        self.reflector.reflect_no_researcher(
            self.curr_state, returns_losses, self.no_memory
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
