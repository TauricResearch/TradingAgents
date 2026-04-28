# TradingAgents/graph/trading_graph.py

import json
import os
from copy import deepcopy
from typing import Any

# Import the new abstract tool methods
from tradingagents.agents.utils.memory import FinancialSituationMemory
from tradingagents.dataflows.config import set_config
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.llm_clients import create_llm_client
from tradingagents.llm_clients.rate_limiter import get_rate_limiter
from tradingagents.memory.news_evidence import NewsEvidenceStore
from tradingagents.report_paths import generate_run_id, get_eval_dir

from ._graph_utils import get_provider_kwargs, visualize_graph
from .conditional_logic import ConditionalLogic
from .propagation import Propagator
from .reflection import Reflector
from .setup import GraphSetup
from .signal_processing import SignalProcessor


class TradingAgentsGraph:
    """Main class that orchestrates the trading agents framework."""

    def __init__(
        self,
        selected_analysts=None,
        debug=False,
        config: dict[str, Any] | None = None,
        callbacks: list | None = None,
    ):
        """Initialize the trading agents graph and components.

        Args:
            selected_analysts: List of analyst types to include
            debug: Whether to run in debug mode
            config: Configuration dictionary. If None, uses default config
            callbacks: Optional list of callback handlers (e.g., for tracking LLM/tool stats)
        """
        if selected_analysts is None:
            selected_analysts = ["market", "news", "fundamentals"]
        self.debug = debug
        self.config = deepcopy(config or DEFAULT_CONFIG)
        self.callbacks = callbacks or []

        # Update the interface's config
        set_config(self.config)

        # Create necessary directories
        os.makedirs(
            os.path.join(self.config["project_dir"], "dataflows/data_cache"),
            exist_ok=True,
        )

        # Initialize LLMs with provider-specific thinking configuration.
        # Per-role provider/backend_url keys take precedence over the shared ones.
        deep_provider, deep_model, deep_backend_url = self._resolve_llm_tier("deep_think")
        mid_provider, mid_model, mid_backend_url = self._resolve_llm_tier("mid_think")
        quick_provider, quick_model, quick_backend_url = self._resolve_llm_tier("quick_think")

        deep_kwargs = self._get_provider_kwargs("deep_think")
        mid_kwargs = self._get_provider_kwargs("mid_think")
        quick_kwargs = self._get_provider_kwargs("quick_think")

        # Add callbacks to kwargs if provided (passed to LLM constructor)
        if self.callbacks:
            deep_kwargs["callbacks"] = self.callbacks
            mid_kwargs["callbacks"] = self.callbacks
            quick_kwargs["callbacks"] = self.callbacks

        # Add per-tier rate limiters when configured via env vars
        for tier, tier_kwargs in (
            ("deep_think", deep_kwargs),
            ("mid_think", mid_kwargs),
            ("quick_think", quick_kwargs),
        ):
            limiter = get_rate_limiter(tier)
            if limiter is not None:
                tier_kwargs["rate_limiter"] = limiter

        deep_client = create_llm_client(
            provider=deep_provider, model=deep_model, base_url=deep_backend_url, **deep_kwargs
        )
        mid_client = create_llm_client(
            provider=mid_provider, model=mid_model, base_url=mid_backend_url, **mid_kwargs
        )
        quick_client = create_llm_client(
            provider=quick_provider, model=quick_model, base_url=quick_backend_url, **quick_kwargs
        )

        self.deep_thinking_llm = deep_client.get_llm()
        self.mid_thinking_llm = mid_client.get_llm()
        self.quick_thinking_llm = quick_client.get_llm()

        # Initialize memories
        self.bull_memory = FinancialSituationMemory("bull_memory", self.config)
        self.bear_memory = FinancialSituationMemory("bear_memory", self.config)
        self.trader_memory = FinancialSituationMemory("trader_memory", self.config)
        self.invest_judge_memory = FinancialSituationMemory("invest_judge_memory", self.config)
        self.portfolio_manager_memory = FinancialSituationMemory(
            "portfolio_manager_memory", self.config
        )
        self.news_evidence_store = NewsEvidenceStore()

        # Initialize components — wire debate/risk rounds from config
        self.conditional_logic = ConditionalLogic(
            max_debate_rounds=self.config.get("max_debate_rounds", 2),
        )
        self.graph_setup = GraphSetup(
            self.quick_thinking_llm,
            self.mid_thinking_llm,
            self.deep_thinking_llm,
            self.bull_memory,
            self.bear_memory,
            self.trader_memory,
            self.invest_judge_memory,
            self.portfolio_manager_memory,
            self.conditional_logic,
            self.news_evidence_store,
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

        # Phase subgraphs (compiled lazily on first access)
        self._debate_graph = None
        self._risk_graph = None

    @property
    def debate_graph(self) -> Any:
        """Subgraph starting from Bull Researcher (skips analysts)."""
        if self._debate_graph is None:
            self._debate_graph = self.graph_setup.build_debate_subgraph()
        return self._debate_graph

    @property
    def risk_graph(self) -> Any:
        """Subgraph starting from Aggressive Analyst (skips analysts + debate + trader)."""
        if self._risk_graph is None:
            self._risk_graph = self.graph_setup.build_risk_subgraph()
        return self._risk_graph

    def _resolve_llm_tier(self, tier: str) -> tuple[str, str, str | None]:
        """Resolve (provider, model, backend_url) for the given LLM tier.

        mid_think falls back to quick_think when not configured.
        """
        if tier == "mid_think":
            model = self.config.get("mid_think_llm") or self.config["quick_think_llm"]
            provider = (
                self.config.get("mid_think_llm_provider")
                or self.config.get("quick_think_llm_provider")
                or self.config["llm_provider"]
            )
            backend_url = (
                self.config.get("mid_think_backend_url")
                or self.config.get("quick_think_backend_url")
                or self.config.get("backend_url")
            )
        else:
            model = self.config[f"{tier}_llm"]
            provider = self.config.get(f"{tier}_llm_provider") or self.config["llm_provider"]
            backend_url = self.config.get(f"{tier}_backend_url") or self.config.get("backend_url")
        return provider, model, backend_url

    def _get_provider_kwargs(self, role: str = "") -> dict[str, Any]:
        """Get provider-specific kwargs for LLM client creation."""
        return get_provider_kwargs(self.config, role)

    def propagate(self, company_name: str, trade_date: str) -> tuple[dict[str, Any], Any]:
        """Run the trading agents graph for a company on a specific date."""

        self.ticker = company_name

        # Initialize state
        init_agent_state = self.propagator.create_initial_state(
            company_name, trade_date, run_id=generate_run_id()
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

            if not trace:
                raise RuntimeError("Graph produced no output during debug streaming.")
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

    def _log_state(self, trade_date: str, final_state: dict[str, Any]) -> None:
        """Log the final state to a JSON file."""
        # Defensive access for nested debate state fields
        investment_debate = final_state.get("investment_debate_state", {})
        risk_debate = final_state.get("risk_debate_state", {})

        self.log_states_dict[str(trade_date)] = {
            "company_of_interest": final_state.get("company_of_interest", ""),
            "trade_date": final_state.get("trade_date", ""),
            "market_report": final_state.get("market_report", ""),
            "macro_regime_report": final_state.get("macro_regime_report", ""),
            "sentiment_report": final_state.get("sentiment_report", ""),
            "news_report": final_state.get("news_report", ""),
            "fundamentals_report": final_state.get("fundamentals_report", ""),
            "research_packet_summary": final_state.get("research_packet_summary", ""),
            "investment_debate_state": {
                "bull_history": investment_debate.get("bull_history", ""),
                "bear_history": investment_debate.get("bear_history", ""),
                "history": investment_debate.get("history", ""),
                "summary": investment_debate.get("summary", ""),
                "current_response": investment_debate.get("current_response", ""),
                "judge_decision": investment_debate.get("judge_decision", ""),
            },
            "trader_investment_decision": final_state.get("trader_investment_plan", ""),
            "risk_debate_state": {
                "aggressive_history": risk_debate.get("aggressive_history", ""),
                "conservative_history": risk_debate.get("conservative_history", ""),
                "neutral_history": risk_debate.get("neutral_history", ""),
                "history": risk_debate.get("history", ""),
                "summary": risk_debate.get("summary", ""),
                "judge_decision": risk_debate.get("judge_decision", ""),
            },
            "investment_plan": final_state.get("investment_plan", ""),
            "final_trade_decision": final_state.get("final_trade_decision", ""),
        }

        # Save to file
        directory = get_eval_dir(str(trade_date), self.ticker)
        directory.mkdir(parents=True, exist_ok=True)

        with open(
            directory / f"full_states_log_{trade_date}.json",
            "w",
            encoding="utf-8",
        ) as f:
            json.dump(self.log_states_dict, f, indent=4)

    def reflect_and_remember(self, returns_losses: float) -> None:
        """Reflect on decisions and update memory based on returns."""
        self.reflector.reflect_bull_researcher(self.curr_state, returns_losses, self.bull_memory)
        self.reflector.reflect_bear_researcher(self.curr_state, returns_losses, self.bear_memory)
        self.reflector.reflect_trader(self.curr_state, returns_losses, self.trader_memory)
        self.reflector.reflect_invest_judge(
            self.curr_state, returns_losses, self.invest_judge_memory
        )
        self.reflector.reflect_portfolio_manager(
            self.curr_state, returns_losses, self.portfolio_manager_memory
        )

    def process_signal(self, full_signal: str) -> Any:
        """Process a signal to extract the core decision."""
        return self.signal_processor.process_signal(full_signal)

    def visualize(
        self, output_path: str | None = None, format: str = "mermaid"
    ) -> str | bytes | None:
        """Visualize the graph in various formats.

        Args:
            output_path: If provided, saves the visualization to this file.
            format: "mermaid", "ascii", or "png".
        """
        return visualize_graph(self.graph, output_path, format)
