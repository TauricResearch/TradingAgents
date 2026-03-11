# TradingAgents/graph/trading_graph.py

import os
from pathlib import Path
import json
from typing import Dict, Any, List, Optional

from langgraph.prebuilt import ToolNode

from tradingagents.llm_clients import create_llm_client
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.agents.utils.memory import FinancialSituationMemory
from tradingagents.dataflows.config import set_config

from tradingagents.agents.utils.agent_utils import (
    get_stock_data,
    get_indicators,
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement,
    get_news,
    get_insider_transactions,
    get_global_news,
    # Korean market tools
    get_krx_stock_data,
    get_krx_indicators,
    get_exchange_rate,
    get_korea_index,
    get_investor_trading,
    get_krx_fundamentals,
    get_dart_financials,
    get_dart_disclosures,
    get_dart_shareholders,
    get_korean_news,
    get_korean_global_news,
)

from .conditional_logic import ConditionalLogic
from .setup import GraphSetup
from .propagation import Propagator
from .reflection import Reflector
from .signal_processing import SignalProcessor


class TradingAgentsGraph:
    """Swing trading graph: Analysts → Trader → Decision.

    Simplified pipeline without debate or risk management stages.
    """

    def __init__(
        self,
        selected_analysts=["market", "news", "fundamentals"],
        debug=False,
        config: Dict[str, Any] = None,
        callbacks: Optional[List] = None,
    ):
        self.debug = debug
        self.config = config or DEFAULT_CONFIG
        self.callbacks = callbacks or []

        set_config(self.config)

        os.makedirs(
            os.path.join(self.config["project_dir"], "dataflows/data_cache"),
            exist_ok=True,
        )

        # Initialize LLMs
        llm_kwargs = self._get_provider_kwargs()
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

        # Only trader memory needed
        self.trader_memory = FinancialSituationMemory("trader_memory", self.config)

        # Create tool nodes
        self.tool_nodes = self._create_tool_nodes()

        # Initialize components
        self.conditional_logic = ConditionalLogic()
        self.graph_setup = GraphSetup(
            self.quick_thinking_llm,
            self.deep_thinking_llm,
            self.tool_nodes,
            self.trader_memory,
            self.conditional_logic,
        )

        self.propagator = Propagator(self.config.get("max_recur_limit", 100))
        self.reflector = Reflector(self.quick_thinking_llm)
        self.signal_processor = SignalProcessor(self.quick_thinking_llm)

        # State tracking
        self.curr_state = None
        self.ticker = None

        # Set up the graph
        self.graph = self.graph_setup.setup_graph(selected_analysts)

    def _get_provider_kwargs(self) -> Dict[str, Any]:
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
        return {
            "market": ToolNode(
                [
                    get_stock_data,
                    get_indicators,
                    get_krx_stock_data,
                    get_krx_indicators,
                    get_exchange_rate,
                    get_korea_index,
                    get_investor_trading,
                ]
            ),
            "news": ToolNode(
                [
                    get_news,
                    get_global_news,
                    get_insider_transactions,
                    get_korean_news,
                    get_korean_global_news,
                    get_dart_disclosures,
                ]
            ),
            "fundamentals": ToolNode(
                [
                    get_fundamentals,
                    get_balance_sheet,
                    get_cashflow,
                    get_income_statement,
                    get_krx_fundamentals,
                    get_dart_financials,
                    get_dart_shareholders,
                ]
            ),
        }

    def propagate(
        self,
        company_name: str,
        trade_date: str,
        screening_context: str = "",
        portfolio_context: str = "",
    ):
        """Run the swing trading graph for a company.

        Args:
            company_name: Ticker symbol
            trade_date: Trading date
            screening_context: Why screener flagged this stock
            portfolio_context: Current portfolio state summary

        Returns:
            (final_state, swing_signal_dict)
        """
        self.ticker = company_name

        init_state = self.propagator.create_initial_state(
            company_name, trade_date, screening_context, portfolio_context
        )
        args = self.propagator.get_graph_args()

        if self.debug:
            trace = []
            for chunk in self.graph.stream(init_state, **args):
                if chunk.get("messages"):
                    chunk["messages"][-1].pretty_print()
                trace.append(chunk)
            final_state = trace[-1]
        else:
            final_state = self.graph.invoke(init_state, **args)

        self.curr_state = final_state
        self._log_state(trade_date, final_state)

        # Process swing signal
        swing_signal = self.signal_processor.process_swing_signal(
            final_state["trader_decision"]
        )
        return final_state, swing_signal

    def _log_state(self, trade_date, final_state):
        """Log the final state to a JSON file."""
        log_data = {
            str(trade_date): {
                "company_of_interest": final_state["company_of_interest"],
                "trade_date": final_state["trade_date"],
                "market_report": final_state["market_report"],
                "news_report": final_state["news_report"],
                "fundamentals_report": final_state["fundamentals_report"],
                "trader_decision": final_state["trader_decision"],
                "swing_order": final_state.get("swing_order", ""),
            }
        }

        directory = Path(
            self.config.get("results_dir", "./results")
        ) / self.ticker / "logs"
        directory.mkdir(parents=True, exist_ok=True)

        with open(directory / f"state_{trade_date}.json", "w") as f:
            json.dump(log_data, f, indent=4, ensure_ascii=False)

    def reflect_and_remember(self, returns_losses):
        """Reflect on trader's decision and update memory."""
        self.reflector.reflect_trader(
            self.curr_state, returns_losses, self.trader_memory
        )

    def process_signal(self, full_signal: str) -> dict:
        """Process a signal to extract swing order parameters."""
        return self.signal_processor.process_swing_signal(full_signal)

    def screen(
        self,
        trade_date: str,
        existing_positions: list[str] | None = None,
        portfolio_context: str = "",
    ) -> dict:
        """Run stock screening to discover swing trading candidates.

        Returns:
            Dict with candidates, report, stats
        """
        from tradingagents.graph.screening_graph import ScreeningGraph

        screener = ScreeningGraph(self.config)
        return screener.run(
            trade_date=trade_date,
            market=self.config.get("market", "KRX"),
            existing_positions=existing_positions,
            portfolio_context=portfolio_context,
            max_candidates=self.config.get("screening_max_candidates", 5),
        )

    def run_swing_pipeline(
        self,
        trade_date: str,
        existing_positions: list[str] | None = None,
        portfolio_context: str = "",
        on_screening_done=None,
        on_candidate_start=None,
        on_candidate_done=None,
    ) -> list[dict]:
        """Full swing trading pipeline: Screen → Analyze each candidate.

        Args:
            trade_date: Trading date
            existing_positions: Tickers already held
            portfolio_context: Portfolio summary
            on_screening_done: Callback(screening_result) after screening
            on_candidate_start: Callback(ticker, screening_context) before analysis
            on_candidate_done: Callback(ticker, final_state, swing_signal) after analysis

        Returns:
            List of dicts: [{ticker, final_state, swing_signal}, ...]
        """
        # Step 1: Screen
        screening_result = self.screen(
            trade_date=trade_date,
            existing_positions=existing_positions,
            portfolio_context=portfolio_context,
        )

        if on_screening_done:
            on_screening_done(screening_result)

        candidates = screening_result.get("candidates", [])
        if not candidates:
            return []

        # Step 2: Analyze each candidate
        results = []
        for candidate in candidates:
            ticker = candidate["ticker"]
            screening_context = (
                f"종목: {candidate['name']} ({ticker})\n"
                f"기술적 신호: {', '.join(candidate.get('signals', []))}\n"
                f"펀더멘탈: {candidate.get('fundamental_check', 'N/A')}"
            )

            if on_candidate_start:
                on_candidate_start(ticker, screening_context)

            try:
                final_state, swing_signal = self.propagate(
                    company_name=ticker,
                    trade_date=trade_date,
                    screening_context=screening_context,
                    portfolio_context=portfolio_context,
                )

                result = {
                    "ticker": ticker,
                    "name": candidate.get("name", ticker),
                    "final_state": final_state,
                    "swing_signal": swing_signal,
                    "screening_context": screening_context,
                }
                results.append(result)

                if on_candidate_done:
                    on_candidate_done(ticker, final_state, swing_signal)

            except Exception as e:
                import logging
                logging.getLogger(__name__).error(
                    f"Analysis failed for {ticker}: {e}"
                )

        return results
