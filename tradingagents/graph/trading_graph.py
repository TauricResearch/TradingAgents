# TradingAgents/graph/trading_graph.py

import logging
import os
from pathlib import Path
import json
from datetime import date, datetime, timedelta
from typing import Dict, Any, Tuple, List, Optional

from langgraph.prebuilt import ToolNode

from tradingagents.llm_clients import create_llm_client

from tradingagents.agents import *
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.agents.utils.memory import FinancialSituationMemory
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
from .structured_signal import (
    extract_structured_strategy,
    StructuredStrategyError,
)


logger = logging.getLogger(__name__)


class TradingAgentsGraph:
    """Main class that orchestrates the trading agents framework."""

    def __init__(
        self,
        selected_analysts=["market", "social", "news", "fundamentals"],
        debug=False,
        config: Dict[str, Any] = None,
        callbacks: Optional[List] = None,
        trading_mode: str = "live",
    ):
        """Initialize the trading agents graph and components.

        Args:
            selected_analysts: List of analyst types to include
            debug: Whether to run in debug mode
            config: Configuration dictionary. If None, uses default config
            callbacks: Optional list of callback handlers (e.g., for tracking LLM/tool stats)
            trading_mode: "backtest" wires the state-first Portfolio Manager;
                anything else uses the legacy live Portfolio Manager.
        """
        self.debug = debug
        self.config = config or DEFAULT_CONFIG
        self.callbacks = callbacks or []
        self.trading_mode = trading_mode

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
            max_analyst_tool_calls=self.config.get("max_analyst_tool_calls"),
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
            trading_mode=self.trading_mode,
            portfolio_state_policy_config=self.config.get("portfolio_state_policy"),
        )

        self.propagator = Propagator()
        self.reflector = Reflector(self.quick_thinking_llm)
        self.signal_processor = SignalProcessor(self.quick_thinking_llm)

        # State tracking
        self.curr_state = None
        self.ticker = None
        self.log_states_dict = {}  # date to full state dict

        # Set up the graph. Keep the workflow so checkpoint mode can recompile
        # it with a saver for this ticker/date.
        self.workflow = self.graph_setup.setup_graph(selected_analysts)
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

    def propagate(
        self,
        company_name,
        trade_date,
        holdings_info: Optional[Dict[str, float]] = None,
        trading_mode: str = "live",
        trading_history_summary: Optional[Dict[str, Any]] = None,
        prior_pending_orders: Optional[List[Dict[str, Any]]] = None,
    ):
        """Run the trading agents graph for a company on a specific date."""

        self.ticker = company_name
        self.trading_mode = trading_mode

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
                    "Resuming from step %d for %s on %s",
                    step,
                    company_name,
                    trade_date,
                )
            else:
                logger.info("Starting fresh for %s on %s", company_name, trade_date)

        try:
            # Initialize state
            init_agent_state = self.propagator.create_initial_state(
                company_name,
                trade_date,
                holdings_info=holdings_info,
                trading_mode=trading_mode,
                trading_history_summary=trading_history_summary,
                prior_pending_orders=prior_pending_orders,
            )
            args = self.propagator.get_graph_args()
            if self.config.get("checkpoint_enabled"):
                tid = thread_id(company_name, str(trade_date))
                args.setdefault("config", {}).setdefault("configurable", {})["thread_id"] = tid

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

            # In backtest mode, also persist the structured strategy JSON.
            if trading_mode == "backtest":
                self._save_backtest_strategy(company_name, trade_date, final_state)
                self._remember_backtest_portfolio_decision(trade_date, final_state)

            if self.config.get("checkpoint_enabled"):
                clear_checkpoint(
                    self.config["data_cache_dir"], company_name, str(trade_date)
                )

            # Return decision and processed signal
            return final_state, self.process_signal(final_state["final_trade_decision"])
        finally:
            if self._checkpointer_ctx is not None:
                self._checkpointer_ctx.__exit__(None, None, None)
                self._checkpointer_ctx = None
                self.graph = self.workflow.compile()

    def _save_backtest_strategy(self, ticker: str, trade_date: str, final_state: Dict[str, Any]) -> Path:
        """Extract and persist the structured strategy JSON to back_test/strategy/{ticker}/."""
        # valid_until needs to comfortably cover the next review cadence even when
        # the cadence straddles a weekend or holiday. 2x cadence + 1 day works for
        # any cadence from 1 to ~30 trading days; the engine caps it tighter via
        # the next strategy's _active_from anyway.
        cadence = int(self.config.get("review_cadence_trading_days") or 5)
        valid_window_days = max(cadence * 2 + 1, 6)

        try:
            strategy = extract_structured_strategy(
                final_state.get("structured_strategy"),
                ticker=ticker,
                trade_date=str(trade_date),
            )
            as_of = datetime.strptime(str(strategy["as_of_date"]), "%Y-%m-%d")
            strategy["valid_until"] = (as_of + timedelta(days=valid_window_days)).strftime("%Y-%m-%d")
            market_state = final_state.get("market_state")
            if market_state:
                strategy["market_state"] = market_state
            structure_analysis = final_state.get("structure_analysis")
            if structure_analysis:
                strategy["structure_analysis"] = structure_analysis
        except StructuredStrategyError as e:
            # Persist a sentinel so the operator knows the run failed extraction.
            as_of = datetime.strptime(str(trade_date), "%Y-%m-%d")
            strategy = {
                "schema_version": "v2",
                "ticker": ticker,
                "as_of_date": str(trade_date),
                "valid_until": (as_of + timedelta(days=valid_window_days)).strftime("%Y-%m-%d"),
                "error": f"structured-extraction-failed: {e}",
                "raw_decision": final_state["final_trade_decision"],
            }

        # Project root = parent of `tradingagents/` package
        safe_ticker = safe_ticker_component(ticker)
        strategy_dir = Path(__file__).resolve().parents[2] / "back_test" / "strategy" / safe_ticker
        strategy_dir.mkdir(parents=True, exist_ok=True)

        out_path = strategy_dir / f"{safe_ticker}_{trade_date}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(strategy, f, indent=2, ensure_ascii=False)
        return out_path

    def _remember_backtest_portfolio_decision(self, trade_date: str, final_state: Dict[str, Any]) -> None:
        """Record the just-finalized portfolio decision without outcome reflection.

        Backtest strategy generation must not use future trades/returns to
        revise earlier decisions. This stores only the as-of reports and the
        finalized decision so later review dates can retrieve prior policy
        context, while `reflect_portfolio_manager()` remains reserved for
        explicit post-outcome reflection.
        """
        situation = (
            f"{final_state['market_report']}\n\n{final_state['sentiment_report']}\n\n"
            f"{final_state['news_report']}\n\n{final_state['fundamentals_report']}"
        )
        decision = final_state["risk_debate_state"]["judge_decision"]
        market_state = final_state.get("market_state")
        market_state_text = f"\nMarketState: {market_state}" if market_state else ""
        recommendation = (
            f"As-of {trade_date} portfolio decision recorded immediately after strategy finalization. "
            "No realized returns, future prices, fills, or post-trade reflection were used.\n"
            f"{decision}{market_state_text}"
        )
        self.portfolio_manager_memory.add_situations([(situation, recommendation)])

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
        }

        # Save to file
        safe_ticker = safe_ticker_component(self.ticker)
        directory = Path(self.config["results_dir"]) / safe_ticker / "TradingAgentsStrategy_logs"
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
