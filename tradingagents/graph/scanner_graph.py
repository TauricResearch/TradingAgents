"""Scanner graph — orchestrates the 4-phase macro scanner pipeline."""

from copy import deepcopy
from typing import Any, List, Optional

from tradingagents.dataflows.config import set_config
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.llm_clients import create_llm_client
from tradingagents.agents.scanners import (
    create_gatekeeper_scanner,
    create_geopolitical_scanner,
    create_market_movers_scanner,
    create_sector_scanner,
    create_factor_alignment_scanner,
    create_drift_scanner,
    create_smart_money_scanner,
    create_industry_deep_dive,
    create_macro_synthesis,
    create_scanner_summarizer,
)
from .scanner_setup import ScannerGraphSetup


class ScannerGraph:
    """Orchestrates the macro scanner pipeline.

    Phase 1a (parallel): gatekeeper_scanner, geopolitical_scanner, market_movers_scanner, sector_scanner
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
        self.config = deepcopy(config or DEFAULT_CONFIG)
        self.debug = debug
        self.callbacks = callbacks or []
        set_config(self.config)

        quick_llm = self._create_llm("quick_think")
        scanner_llm = self._create_llm("scanner")
        mid_llm = self._create_llm("mid_think")
        deep_llm = self._create_llm("deep_think")

        max_scan_tickers = int(self.config.get("max_auto_tickers", 10))
        scan_horizon_days = int(self.config.get("scan_horizon_days", 30))

        # Scanner nodes use the scanner_llm tier (tool-call compliant model).
        # Summarizers use quick_llm (no tool calling needed).
        self.agents = {
            "gatekeeper_scanner": create_gatekeeper_scanner(scanner_llm),
            "geopolitical_scanner": create_geopolitical_scanner(scanner_llm),
            "market_movers_scanner": create_market_movers_scanner(scanner_llm),
            "sector_scanner": create_sector_scanner(scanner_llm),
            "factor_alignment_scanner": create_factor_alignment_scanner(scanner_llm),
            "drift_scanner": create_drift_scanner(scanner_llm),
            "smart_money_scanner": create_smart_money_scanner(scanner_llm),
            "industry_deep_dive": create_industry_deep_dive(mid_llm),
            "macro_synthesis": create_macro_synthesis(
                deep_llm,
                max_scan_tickers=max_scan_tickers,
                scan_horizon_days=scan_horizon_days,
            ),
            # Summarizers
            "summarize_gatekeeper": create_scanner_summarizer(
                quick_llm, "gatekeeper_universe_report", "gatekeeper_summary"
            ),
            "summarize_geopolitical": create_scanner_summarizer(
                quick_llm, "geopolitical_report", "geopolitical_summary"
            ),
            "summarize_market_movers": create_scanner_summarizer(
                quick_llm, "market_movers_report", "market_movers_summary"
            ),
            "summarize_sector": create_scanner_summarizer(
                quick_llm, "sector_performance_report", "sector_summary"
            ),
            "summarize_factor_alignment": create_scanner_summarizer(
                quick_llm, "factor_alignment_report", "factor_alignment_summary"
            ),
            "summarize_drift": create_scanner_summarizer(
                quick_llm, "drift_opportunities_report", "drift_opportunities_summary"
            ),
            "summarize_smart_money": create_scanner_summarizer(
                quick_llm, "smart_money_report", "smart_money_summary"
            ),
            "summarize_industry_deep_dive": create_scanner_summarizer(
                quick_llm, "industry_deep_dive_report", "industry_deep_dive_summary"
            ),
        }

        setup = ScannerGraphSetup(self.agents)
        self.setup = setup
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

        if tier == "scanner":
            # Scanner tier falls back to quick_think when unset.
            model = (
                self.config.get("scanner_llm")
                or self.config["quick_think_llm"]
            )
            provider = (
                self.config.get("scanner_llm_provider")
                or self.config.get("quick_think_llm_provider")
                or self.config["llm_provider"]
            )
            backend_url = (
                self.config.get("scanner_backend_url")
                or self.config.get("quick_think_backend_url")
                or self.config.get("backend_url")
            )
        elif tier == "mid_think":
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
        # Scanner tier resolves provider kwargs through quick_think when unset.
        if tier == "scanner":
            prefix = "scanner_"
            fallback_prefix = "quick_think_"
        else:
            prefix = f"{tier}_"
            fallback_prefix = None
        provider = (
            self.config.get(f"{prefix}llm_provider")
            or (self.config.get(f"{fallback_prefix}llm_provider") if fallback_prefix else None)
            or self.config.get("llm_provider", "")
        ).lower()
        timeout = self.config.get(f"{prefix}llm_timeout")
        if timeout is None and fallback_prefix:
            timeout = self.config.get(f"{fallback_prefix}llm_timeout")
        if timeout is None:
            timeout = self.config.get("llm_timeout")
        if timeout is not None:
            kwargs["timeout"] = float(timeout)

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
            "gatekeeper_universe_report": "",
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

    def graph_from(self, start_node: str):
        """Return a compiled partial scanner graph that starts at *start_node*."""
        return self.setup.setup_graph_from(start_node)
