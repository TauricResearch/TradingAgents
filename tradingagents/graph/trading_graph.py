"""Main orchestrator for the structured equity ranking engine.

Replaces the old TradingAgentsGraph with a tiered Pydantic-based pipeline.
"""

from __future__ import annotations

import json
import os
import logging
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.llm_clients import create_llm_client
from tradingagents.dataflows.config import set_config

from .setup import StructuredGraphSetup

logger = logging.getLogger(__name__)


class TradingAgentsGraph:
    """Structured equity ranking engine built on LangGraph."""

    def __init__(
        self,
        selected_analysts=None,  # ignored — all agents run in structured pipeline
        debug=False,
        config: Optional[Dict[str, Any]] = None,
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

        # Build the structured pipeline graph
        graph_setup = StructuredGraphSetup(
            self.quick_thinking_llm, self.deep_thinking_llm
        )
        self.graph = graph_setup.setup_graph()

        # State tracking
        self.curr_state = None
        self.ticker = None

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

    async def propagate(self, company_name: str, trade_date: str):
        """Run the structured pipeline for a company (async — parallel nodes)."""
        import asyncio

        self.ticker = company_name
        init_state = self._create_initial_state(company_name, trade_date)
        args = {"config": {"recursion_limit": 50}}

        if self.debug:
            trace = []
            async for chunk in self.graph.astream(init_state, stream_mode="values", **args):
                trace.append(chunk)
            final_state = trace[-1] if trace else init_state
        else:
            final_state = await self.graph.ainvoke(init_state, **args)

        self.curr_state = final_state
        self._log_state(trade_date, final_state)

        decision = final_state.get("final_decision") or {}
        signal = decision.get("action", "AVOID")
        return final_state, signal

    def _create_initial_state(self, ticker: str, trade_date: str) -> Dict[str, Any]:
        return {
            "ticker": ticker.upper(),
            "trade_date": str(trade_date),
            "validation": None,
            "company_card": None,
            "macro": None,
            "liquidity": None,
            "sector_rotation": None,
            "business_quality": None,
            "institutional_flow": None,
            "valuation": None,
            "entry_timing": None,
            "earnings_revisions": None,
            "backlog": None,
            "crowding": None,
            "archetype": None,
            "master_score": None,
            "adjusted_score": None,
            "position_role": None,
            "theme_substitution": None,
            "position_replacement": None,
            "bull_case": None,
            "bear_case": None,
            "debate": None,
            "risk": None,
            "final_decision": None,
            "hard_veto": False,
            "hard_veto_reason": None,
            "global_flags": [],
        }

    def _log_state(self, trade_date: str, state: Dict[str, Any]):
        """Log the final state to JSON."""
        log_data = {
            "ticker": state.get("ticker"),
            "trade_date": str(trade_date),
            "master_score": state.get("master_score"),
            "adjusted_score": state.get("adjusted_score"),
            "position_role": state.get("position_role"),
            "hard_veto": state.get("hard_veto"),
            "validation": state.get("validation"),
            "company_card": state.get("company_card"),
            "macro": state.get("macro"),
            "liquidity": state.get("liquidity"),
            "business_quality": state.get("business_quality"),
            "institutional_flow": state.get("institutional_flow"),
            "valuation": state.get("valuation"),
            "entry_timing": state.get("entry_timing"),
            "earnings_revisions": state.get("earnings_revisions"),
            "sector_rotation": state.get("sector_rotation"),
            "backlog": state.get("backlog"),
            "crowding": state.get("crowding"),
            "archetype": state.get("archetype"),
            "theme_substitution": state.get("theme_substitution"),
            "position_replacement": state.get("position_replacement"),
            "bull_case": state.get("bull_case"),
            "bear_case": state.get("bear_case"),
            "debate": state.get("debate"),
            "risk": state.get("risk"),
            "final_decision": state.get("final_decision"),
        }

        directory = Path(f"eval_results/{self.ticker}/StructuredPipeline_logs/")
        directory.mkdir(parents=True, exist_ok=True)

        filepath = directory / f"analysis_{trade_date}.json"
        with open(filepath, "w") as f:
            json.dump(log_data, f, indent=2, default=str)
        logger.info("State logged to %s", filepath)

    def process_signal(self, decision_text: str) -> str:
        """Extract signal from decision text (legacy compatibility)."""
        if isinstance(decision_text, dict):
            return decision_text.get("action", "AVOID")
        text = str(decision_text).upper()
        if "BUY" in text:
            return "BUY"
        if "SELL" in text:
            return "SELL"
        if "HOLD" in text:
            return "HOLD"
        return "AVOID"

    def reflect_and_remember(self, returns_losses):
        """No-op for structured pipeline (no BM25 memory)."""
        pass
