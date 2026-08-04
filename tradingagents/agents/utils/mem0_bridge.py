"""mem0-backed semantic decision memory for TradingAgents.

Complements the existing ``TradingMemoryLog`` (append-only markdown, matched by
ticker) with a semantic memory layer: mem0 stores each decision as an embedding
and retrieves past decisions by *meaning*, not just ticker. This surfaces
relevant cross-ticker lessons ("I've seen this Fed-pivot pattern before") that
ticker-based matching misses.

The bridge is opt-in: when ``TRADINGAGENTS_MEM0_ENABLED=1`` is unset (default),
all calls are no-ops, so the existing pipeline is unaffected. Enable it to let
the Portfolio Manager benefit from semantic recall of past decisions.

Usage in trading_graph._run_graph::

    from tradingagents.agents.utils.mem0_bridge import Mem0Bridge

    bridge = Mem0Bridge.from_config(self.config)
    past_context = self.memory_log.get_past_context(company_name)
    past_context += bridge.recall_relevant(company_name, final_state)
    ...
    bridge.remember_decision(company_name, trade_date, final_state["final_trade_decision"])
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Callable

_ENABLED = os.environ.get("TRADINGAGENTS_MEM0_ENABLED", "").lower() in ("1", "true", "yes")


class Mem0Bridge:
    """Semantic decision memory backed by mem0.

    All methods are no-ops when the bridge is disabled, so callers don't need
    feature-flag checks at every call site.
    """

    _USER_ID = "tradingagents"  # mem0 namespace for all trading decisions

    def __init__(self, memory: Any | None) -> None:
        self._memory = memory

    @classmethod
    def from_config(cls, config: dict | None = None) -> "Mem0Bridge":
        """Build a bridge from config. No-op if disabled or mem0 unavailable."""
        if not _ENABLED:
            return cls(memory=None)
        try:
            from tradingagents.llm_clients.proxy_clients import make_mem0_memory

            return cls(memory=make_mem0_memory())
        except Exception as exc:
            logger.warning("Mem0Bridge disabled: %s", exc)
            return cls(memory=None)

    @property
    def enabled(self) -> bool:
        return self._memory is not None

    def remember_decision(self, ticker: str, trade_date: str, final_decision: str) -> None:
        """Store a completed decision for future semantic recall."""
        if not self.enabled:
            return
        messages = [
            {
                "role": "user",
                "content": f"Trading decision for {ticker} on {trade_date}: {final_decision[:500]}",
            },
            {
                "role": "assistant",
                "content": f"Stored decision for {ticker} ({trade_date}) for future reference.",
            },
        ]
        self._memory.add(
            messages, user_id=self._USER_ID, metadata={"ticker": ticker, "date": trade_date}
        )

    def recall_relevant(self, ticker: str, state: dict) -> str:
        """Retrieve semantically similar past decisions as context text.

        Returns an empty string when disabled or no relevant memories exist.
        """
        if not self.enabled:
            return ""
        # Use the current investment plan + trader proposal as the semantic
        # probe — they capture the decision rationale.
        probe = " ".join(
            str(state.get(k, ""))
            for k in ("investment_plan", "trader_investment_plan", "final_trade_decision")
        )[:500]
        results = self._memory.search(
            query=probe or ticker,
            filters={"user_id": self._USER_ID},
            top_k=3,
        )
        memories = results.get("results", []) if isinstance(results, dict) else []
        if not memories:
            return ""
        lines = [f"- Past decision ({m.get('memory', '')[:150]})" for m in memories[:3]]
        header = (
            f"Semantically recalled past decisions (cross-ticker lessons relevant to {ticker}):"
        )
        return "\n" + header + "\n" + "\n".join(lines)
