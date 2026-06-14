"""Per-run LLM usage and cost accounting.

A provider-agnostic LangChain callback that aggregates token usage and call
counts across every LLM/tool call in a run, so a framework whose value is "many
agents debating" can report what a run actually consumed instead of leaving
users blind. Token counts come from each provider's ``usage_metadata`` (the
normalized field LangChain populates for OpenAI/Anthropic/Google/etc.).

Cost is only estimated when prices are supplied (``model_prices``) — we do not
ship a built-in price table that would silently go stale.
"""

from __future__ import annotations

import threading
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage
from langchain_core.outputs import LLMResult


class UsageTrackingCallback(BaseCallbackHandler):
    """Aggregate LLM call counts, tool call counts, and token usage.

    Args:
        model_prices: optional ``{"input": usd_per_1M, "output": usd_per_1M}``.
            When provided, ``estimated_cost_usd`` and the summary include a
            dollar estimate; otherwise cost is ``None``.
    """

    def __init__(self, model_prices: dict[str, float] | None = None) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self.llm_calls = 0
        self.tool_calls = 0
        self.tokens_in = 0
        self.tokens_out = 0
        self.model_prices = model_prices

    # LangChain may emit on_llm_start (completion models) or on_chat_model_start
    # (chat models) — count both so the tally is provider-shape agnostic.
    def on_llm_start(self, serialized: dict[str, Any], prompts: list[str], **kwargs: Any) -> None:
        with self._lock:
            self.llm_calls += 1

    def on_chat_model_start(
        self, serialized: dict[str, Any], messages: list[list[Any]], **kwargs: Any
    ) -> None:
        with self._lock:
            self.llm_calls += 1

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        try:
            generation = response.generations[0][0]
        except (IndexError, TypeError):
            return
        usage_metadata = None
        message = getattr(generation, "message", None)
        if isinstance(message, AIMessage):
            usage_metadata = getattr(message, "usage_metadata", None)
        if usage_metadata:
            with self._lock:
                self.tokens_in += usage_metadata.get("input_tokens", 0) or 0
                self.tokens_out += usage_metadata.get("output_tokens", 0) or 0

    def on_tool_start(self, serialized: dict[str, Any], input_str: str, **kwargs: Any) -> None:
        with self._lock:
            self.tool_calls += 1

    def estimated_cost_usd(self) -> float | None:
        """Dollar estimate from token counts, or None if no prices were given."""
        if not self.model_prices:
            return None
        in_rate = self.model_prices.get("input", 0.0)
        out_rate = self.model_prices.get("output", 0.0)
        with self._lock:
            return (self.tokens_in / 1_000_000) * in_rate + (
                self.tokens_out / 1_000_000
            ) * out_rate

    def summary(self) -> dict[str, Any]:
        """Machine-readable usage summary (used by the run manifest)."""
        with self._lock:
            data = {
                "llm_calls": self.llm_calls,
                "tool_calls": self.tool_calls,
                "tokens_in": self.tokens_in,
                "tokens_out": self.tokens_out,
                "tokens_total": self.tokens_in + self.tokens_out,
            }
        data["estimated_cost_usd"] = self.estimated_cost_usd()
        return data

    def format_summary(self) -> str:
        """One-line human-readable summary for end-of-run logging."""
        s = self.summary()
        cost = s["estimated_cost_usd"]
        cost_str = (
            f", est. cost ${cost:.4f}"
            if cost is not None
            else " (set config['model_prices'] to estimate cost)"
        )
        return (
            f"Usage: {s['llm_calls']} LLM calls, {s['tool_calls']} tool calls, "
            f"{s['tokens_in']:,} in / {s['tokens_out']:,} out "
            f"({s['tokens_total']:,} tokens){cost_str}"
        )
