"""Portfolio Manager graph — orchestrates the full PM workflow."""

from __future__ import annotations

import uuid
from copy import deepcopy
from typing import Any

from tradingagents.agents.portfolio import (
    create_holding_reviewer,
    create_macro_summary_agent,
    create_micro_summary_agent,
    create_pm_decision_agent,
)
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.llm_clients import create_llm_client
from tradingagents.llm_clients.rate_limiter import get_rate_limiter
from tradingagents.memory.macro_memory import MacroMemory
from tradingagents.memory.reflexion import ReflexionMemory

from ._graph_utils import get_provider_kwargs, visualize_graph
from .portfolio_setup import PortfolioGraphSetup


class PortfolioGraph:
    """Orchestrates the Portfolio Manager workflow.

    Current phases:
    1. load_portfolio — fetch portfolio + holdings from DB
    2. compute_risk — compute portfolio risk metrics
    3. review_holdings — LLM reviews all open positions (mid_think)
    4. prioritize_candidates — score and rank scanner candidates
    5. macro_summary + micro_summary — parallel summary fan-out
    6. pm_decision — LLM produces BUY/SELL/HOLD decisions (deep_think)
    7. cash_sweep — deterministic post-processing step
    8. execute_trades — execute decisions and take EOD snapshot
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        debug: bool = False,
        callbacks: list | None = None,
        repo: Any = None,
    ) -> None:
        """Initialize the portfolio graph.

        Args:
            config: Configuration dictionary.  Falls back to DEFAULT_CONFIG.
            debug: Whether to print intermediate state chunks during streaming.
            callbacks: Optional LangChain callback handlers.
            repo: PortfolioRepository instance.  If None, created lazily from DB.
        """
        self.config = deepcopy(config or DEFAULT_CONFIG)
        self.debug = debug
        self.callbacks = callbacks or []
        self._repo = repo

        mid_llm = self._create_llm("mid_think")
        deep_llm = self._create_llm("deep_think")

        portfolio_config = self._get_portfolio_config()

        mongo_uri = self.config.get("mongo_uri")
        macro_mem = MacroMemory(mongo_uri=mongo_uri)
        micro_mem = ReflexionMemory(
            mongo_uri=mongo_uri,
            collection_name="micro_reflexion",
            fallback_path="reports/micro_reflexion.json",  # distinct from pipeline reflexion.json
        )

        agents = {
            "review_holdings": create_holding_reviewer(mid_llm),
            "macro_summary": create_macro_summary_agent(mid_llm, macro_mem),
            "micro_summary": create_micro_summary_agent(mid_llm, micro_mem),
            "pm_decision": create_pm_decision_agent(
                deep_llm,
                config=portfolio_config,
                macro_memory=macro_mem,
                micro_memory=micro_mem,
            ),
        }

        setup = PortfolioGraphSetup(
            agents,
            repo=self._repo,
            config=portfolio_config,
            macro_memory=macro_mem,
            micro_memory=micro_mem,
        )
        self.graph = setup.setup_graph()

    def _get_portfolio_config(self) -> dict[str, Any]:
        """Extract portfolio-specific config keys."""
        from tradingagents.portfolio.config import get_portfolio_config

        return get_portfolio_config()

    def _create_llm(self, tier: str) -> Any:
        """Create an LLM instance for the given tier.

        Mirrors ScannerGraph._create_llm logic exactly.

        Args:
            tier: One of ``"quick_think"``, ``"mid_think"``, ``"deep_think"``.

        Returns:
            A LangChain-compatible chat model instance.
        """
        kwargs = self._get_provider_kwargs(tier)

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

        if self.callbacks:
            kwargs["callbacks"] = self.callbacks

        limiter = get_rate_limiter(tier)
        if limiter is not None:
            kwargs["rate_limiter"] = limiter

        client = create_llm_client(
            provider=provider,
            model=model,
            base_url=backend_url,
            **kwargs,
        )
        return client.get_llm()

    def _get_provider_kwargs(self, tier: str) -> dict[str, Any]:
        """Resolve provider-specific kwargs (e.g. thinking_level, reasoning_effort)."""
        return get_provider_kwargs(self.config, tier)

    def run(
        self,
        portfolio_id: str,
        date: str,
        prices: dict[str, float],
        scan_summary: dict[str, Any],
        run_id: str | None = None,
    ) -> dict[str, Any]:
        """Run the full portfolio manager workflow.

        Args:
            portfolio_id: ID of the portfolio to manage.
            date: Analysis date string (YYYY-MM-DD).
            prices: Current EOD prices (ticker → price).
            scan_summary: Macro scan output from ScannerGraph (contains
                          ``stocks_to_investigate`` and optionally
                          ``price_histories``).
            run_id: Optional run provenance ID. Generated when omitted.

        Returns:
            Final LangGraph state dict containing all workflow outputs.
        """
        effective_run_id = run_id if run_id else str(uuid.uuid4())

        initial_state: dict[str, Any] = {
            "portfolio_id": portfolio_id,
            "analysis_date": date,
            "run_id": effective_run_id,
            "prices": prices,
            "scan_summary": scan_summary,
            "messages": [],
            "portfolio_data": "",
            "risk_metrics": "",
            "holding_reviews": "",
            "prioritized_candidates": "",
            "macro_brief": "",
            "micro_brief": "",
            "macro_memory_context": "",
            "micro_memory_context": "",
            "pm_decision": "",
            "cash_sweep": "",
            "execution_result": "",
            "sender": "",
            "ticker_analyses": {},
        }

        if self.debug:
            final_state = {}
            for chunk in self.graph.stream(initial_state):
                print(f"[portfolio debug] chunk keys: {list(chunk.keys())}")
                final_state.update(chunk)
            return final_state

        return self.graph.invoke(initial_state)

    def visualize(
        self, output_path: str | None = None, format: str = "mermaid"
    ) -> str | bytes | None:
        """Visualize the graph in various formats.

        Args:
            output_path: If provided, saves the visualization to this file.
            format: "mermaid", "ascii", or "png".
        """
        return visualize_graph(self.graph, output_path, format)
