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
from tradingagents.memory.news_evidence import NewsEvidenceStore
from tradingagents.report_paths import generate_run_id

from .conditional_logic import ConditionalLogic
from .propagation import Propagator
from .reflection import Reflector
from .setup import GraphSetup
from .signal_processing import SignalProcessor


class TradingAgentsGraph:
    """Main class that orchestrates the trading agents framework."""

    def __init__(
        self,
        selected_analysts=["market", "news", "fundamentals"],
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
        deep_kwargs = self._get_provider_kwargs("deep_think")
        mid_kwargs = self._get_provider_kwargs("mid_think")
        quick_kwargs = self._get_provider_kwargs("quick_think")

        # Add callbacks to kwargs if provided (passed to LLM constructor)
        if self.callbacks:
            deep_kwargs["callbacks"] = self.callbacks
            mid_kwargs["callbacks"] = self.callbacks
            quick_kwargs["callbacks"] = self.callbacks

        deep_provider = (
            self.config.get("deep_think_llm_provider") or self.config["llm_provider"]
        )
        deep_backend_url = (
            self.config.get("deep_think_backend_url") or self.config.get("backend_url")
        )
        quick_provider = (
            self.config.get("quick_think_llm_provider") or self.config["llm_provider"]
        )
        quick_backend_url = (
            self.config.get("quick_think_backend_url") or self.config.get("backend_url")
        )

        # mid_think falls back to quick_think when not configured
        mid_model = self.config.get("mid_think_llm") or self.config["quick_think_llm"]
        mid_provider = (
            self.config.get("mid_think_llm_provider")
            or self.config.get("quick_think_llm_provider")
            or self.config["llm_provider"]
        )
        mid_backend_url = (
            self.config.get("mid_think_backend_url")
            or self.config.get("quick_think_backend_url")
            or self.config.get("backend_url")
        )

        deep_client = create_llm_client(
            provider=deep_provider,
            model=self.config["deep_think_llm"],
            base_url=deep_backend_url,
            **deep_kwargs,
        )
        mid_client = create_llm_client(
            provider=mid_provider,
            model=mid_model,
            base_url=mid_backend_url,
            **mid_kwargs,
        )
        quick_client = create_llm_client(
            provider=quick_provider,
            model=self.config["quick_think_llm"],
            base_url=quick_backend_url,
            **quick_kwargs,
        )

        self.deep_thinking_llm = deep_client.get_llm()
        self.mid_thinking_llm = mid_client.get_llm()
        self.quick_thinking_llm = quick_client.get_llm()
        
        # Initialize memories
        self.bull_memory = FinancialSituationMemory("bull_memory", self.config)
        self.bear_memory = FinancialSituationMemory("bear_memory", self.config)
        self.trader_memory = FinancialSituationMemory("trader_memory", self.config)
        self.invest_judge_memory = FinancialSituationMemory("invest_judge_memory", self.config)
        self.portfolio_manager_memory = FinancialSituationMemory("portfolio_manager_memory", self.config)
        self.news_evidence_store = NewsEvidenceStore()

        # Initialize components — wire debate/risk rounds from config
        self.conditional_logic = ConditionalLogic(
            max_debate_rounds=self.config.get("max_debate_rounds", 2),
            max_risk_discuss_rounds=self.config.get("max_risk_discuss_rounds", 2),
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
            self._debate_graph = self.setup.build_debate_subgraph()
        return self._debate_graph

    @property
    def risk_graph(self) -> Any:
        """Subgraph starting from Aggressive Analyst (skips analysts + debate + trader)."""
        if self._risk_graph is None:
            self._risk_graph = self.setup.build_risk_subgraph()
        return self._risk_graph


    def _get_provider_kwargs(self, role: str = "") -> dict[str, Any]:
        """Get provider-specific kwargs for LLM client creation.

        Args:
            role: Either "deep_think" or "quick_think".  When provided the
                  per-role config keys take precedence over the shared keys.
        """
        kwargs = {}
        prefix = f"{role}_" if role else ""
        provider = (
            self.config.get(f"{prefix}llm_provider")
            or self.config.get("llm_provider", "")
        ).lower()
        timeout = self.config.get(f"{prefix}llm_timeout")
        if timeout is None:
            timeout = self.config.get("llm_timeout")
        if timeout is not None:
            kwargs["timeout"] = float(timeout)

        if provider == "google":
            thinking_level = (
                self.config.get(f"{prefix}google_thinking_level")
                or self.config.get("google_thinking_level")
            )
            if thinking_level:
                kwargs["thinking_level"] = thinking_level

        elif provider in ("openai", "xai", "openrouter", "ollama"):
            reasoning_effort = (
                self.config.get(f"{prefix}openai_reasoning_effort")
                or self.config.get("openai_reasoning_effort")
            )
            if reasoning_effort:
                kwargs["reasoning_effort"] = reasoning_effort

        elif provider == "anthropic":
            effort = self.config.get("anthropic_effort")
            if effort:
                kwargs["effort"] = effort

        return kwargs

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
            "company_of_interest": final_state["company_of_interest"],
            "trade_date": final_state["trade_date"],
            "market_report": final_state["market_report"],
            "macro_regime_report": final_state.get("macro_regime_report", ""),
            "sentiment_report": final_state["sentiment_report"],
            "news_report": final_state["news_report"],
            "fundamentals_report": final_state["fundamentals_report"],
            "research_packet_summary": final_state.get("research_packet_summary", ""),
            "investment_debate_state": {
                "bull_history": investment_debate.get("bull_history", ""),
                "bear_history": investment_debate.get("bear_history", ""),
                "history": investment_debate.get("history", ""),
                "summary": investment_debate.get("summary", ""),
                "current_response": investment_debate.get("current_response", ""),
                "judge_decision": investment_debate.get("judge_decision", ""),
            },
            "trader_investment_decision": final_state["trader_investment_plan"],
            "risk_debate_state": {
                "aggressive_history": risk_debate.get("aggressive_history", ""),
                "conservative_history": risk_debate.get("conservative_history", ""),
                "neutral_history": risk_debate.get("neutral_history", ""),
                "history": risk_debate.get("history", ""),
                "summary": risk_debate.get("summary", ""),
                "judge_decision": risk_debate.get("judge_decision", ""),
            },
            "investment_plan": final_state["investment_plan"],
            "final_trade_decision": final_state["final_trade_decision"],
        }

        # Save to file
        from tradingagents.report_paths import get_eval_dir

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

    def process_signal(self, full_signal: str) -> Any:
        """Process a signal to extract the core decision."""
        return self.signal_processor.process_signal(full_signal)

    def visualize(self, output_path: str | None = None, format: str = "mermaid") -> str | bytes | None:
        """Visualize the graph in various formats.

        Args:
            output_path: If provided, saves the visualization to this file.
            format: "mermaid", "ascii", or "png".
        """
        graph = self.graph.get_graph()
        if format == "ascii":
            try:
                res = graph.print_ascii()
            except Exception as e:
                res = f"Could not print ASCII: {e}"
                print(res)
            if output_path:
                with open(output_path, "w") as f:
                    f.write(res if isinstance(res, str) else "ASCII representation printed to console.")
            return res
        elif format == "png":
            png_data = graph.draw_mermaid_png()
            if output_path:
                with open(output_path, "wb") as f:
                    f.write(png_data)
            return png_data
        else:
            mermaid_code = graph.draw_mermaid()
            if output_path:
                with open(output_path, "w") as f:
                    f.write(mermaid_code)
            return mermaid_code
