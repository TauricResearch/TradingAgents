"""Scanner graph — orchestrates the 4-phase macro scanner pipeline."""

from typing import Any, List, Optional

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.llm_clients import create_llm_client
from tradingagents.agents.scanners import (
    create_geopolitical_scanner,
    create_market_movers_scanner,
    create_sector_scanner,
    create_factor_alignment_scanner,
    create_drift_scanner,
    create_smart_money_scanner,
    create_industry_deep_dive,
    create_macro_synthesis,
)
from .scanner_setup import ScannerGraphSetup


class ScannerGraph:
    """Orchestrates the macro scanner pipeline.

    Phase 1a (parallel): geopolitical_scanner, market_movers_scanner, sector_scanner
    Phase 1b (bounded global follow-ons): factor_alignment_scanner, smart_money_scanner
    Phase 1c (after market + sector): drift_scanner
    Phase 2: industry_deep_dive (fan-in from all Phase 1 nodes)
    Phase 3: macro_synthesis -> END
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        debug: bool = False,
        callbacks: Optional[List] = None,
    ) -> None:
        """Initialize the scanner graph.

        Args:
            config: Configuration dictionary. Falls back to DEFAULT_CONFIG when None.
            debug: Whether to stream and print intermediate states.
            callbacks: Optional LangChain callback handlers (e.g. RunLogger.callback).
        """
        self.config = config or DEFAULT_CONFIG.copy()
        self.debug = debug
        self.callbacks = callbacks or []

        quick_llm = self._create_llm("quick_think")
        mid_llm = self._create_llm("mid_think")
        deep_llm = self._create_llm("deep_think")

        max_scan_tickers = int(self.config.get("max_auto_tickers", 10))
        scan_horizon_days = int(self.config.get("scan_horizon_days", 30))

        agents = {
            "geopolitical_scanner": create_geopolitical_scanner(quick_llm),
            "market_movers_scanner": create_market_movers_scanner(quick_llm),
            "sector_scanner": create_sector_scanner(quick_llm),
            "factor_alignment_scanner": create_factor_alignment_scanner(quick_llm),
            "drift_scanner": create_drift_scanner(quick_llm),
            "smart_money_scanner": create_smart_money_scanner(quick_llm),
            "industry_deep_dive": create_industry_deep_dive(mid_llm),
            "macro_synthesis": create_macro_synthesis(
                deep_llm,
                max_scan_tickers=max_scan_tickers,
                scan_horizon_days=scan_horizon_days,
            ),
        }

        setup = ScannerGraphSetup(agents)
        self.graph = setup.setup_graph()

    def _create_llm(self, tier: str) -> Any:
        """Create an LLM instance for the given tier.

        Mirrors the provider/model/backend_url resolution logic from
        TradingAgentsGraph, including mid_think fallback to quick_think.

        Args:
            tier: One of "quick_think", "mid_think", or "deep_think".

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

        client = create_llm_client(
            provider=provider,
            model=model,
            base_url=backend_url,
            **kwargs,
        )
        return client.get_llm()

    def _get_provider_kwargs(self, tier: str) -> dict[str, Any]:
        """Resolve provider-specific kwargs (e.g. thinking_level, reasoning_effort).

        Args:
            tier: One of "quick_think", "mid_think", or "deep_think".

        Returns:
            Dict of extra kwargs to pass to the LLM client constructor.
        """
        kwargs: dict[str, Any] = {}
        prefix = f"{tier}_"
        provider = (
            self.config.get(f"{prefix}llm_provider") or self.config.get("llm_provider", "")
        ).lower()

        if provider == "google":
            thinking_level = self.config.get(f"{prefix}google_thinking_level") or self.config.get(
                "google_thinking_level"
            )
            if thinking_level:
                kwargs["thinking_level"] = thinking_level

        elif provider in ("openai", "xai", "openrouter", "ollama"):
            reasoning_effort = self.config.get(
                f"{prefix}openai_reasoning_effort"
            ) or self.config.get("openai_reasoning_effort")
            if reasoning_effort:
                kwargs["reasoning_effort"] = reasoning_effort

        return kwargs

    def scan(self, scan_date: str) -> dict:
        """Run the scanner pipeline and return the final state.

        Args:
            scan_date: Date string in YYYY-MM-DD format for the scan.

        Returns:
            Final LangGraph state dict containing all scanner reports and
            the macro_scan_summary produced by the synthesis phase.
        """
        initial_state: dict[str, Any] = {
            "scan_date": scan_date,
            "messages": [],
            "geopolitical_report": "",
            "market_movers_report": "",
            "sector_performance_report": "",
            "factor_alignment_report": "",
            "drift_opportunities_report": "",
            "smart_money_report": "",
            "industry_deep_dive_report": "",
            "macro_scan_summary": "",
            "sender": "",
        }

        if self.debug:
            # stream() yields partial state updates; use invoke() for the
            # full accumulated state and print chunks for debugging only.
            for chunk in self.graph.stream(initial_state):
                print(f"[scanner debug] chunk keys: {list(chunk.keys())}")
            # Fall through to invoke() for the correct accumulated result

        return self.graph.invoke(initial_state)
