"""LangChain callback handler that tracks LLM/tool usage for an analysis run.

Register a single instance in the graph run config (``config["callbacks"]``)
so LangChain propagates it to every nested LLM and tool call — that way one
handler captures the whole run without double-counting.
"""
from __future__ import annotations

import logging
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler

_logger = logging.getLogger(__name__)


class StatsCallbackHandler(BaseCallbackHandler):
    """Counts LLM calls, tool calls and input/output tokens during a run."""

    def __init__(self) -> None:
        self.llm_calls = 0
        self.tool_calls = 0
        self.tokens_in = 0
        self.tokens_out = 0

    # ── LLM call counting ──────────────────────────────────────────────────────
    def on_chat_model_start(self, *args: Any, **kwargs: Any) -> None:
        self.llm_calls += 1

    def on_llm_start(self, *args: Any, **kwargs: Any) -> None:
        # Some providers emit on_llm_start instead of on_chat_model_start.
        # Only count here if the chat-model hook is not the one firing; to keep
        # this simple and avoid double counting we rely on chat_model_start for
        # chat models and this for plain-completion models. Chat models do NOT
        # call on_llm_start, so counting here is safe.
        self.llm_calls += 1

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        """Pull token usage from the LLMResult across the various shapes
        different LangChain provider integrations use."""
        try:
            usage = self._extract_usage(response)
            self.tokens_in += int(usage.get("input", 0) or 0)
            self.tokens_out += int(usage.get("output", 0) or 0)
        except Exception:  # never let stats accounting break a run
            pass

    # ── Tool call counting ─────────────────────────────────────────────────────
    def on_tool_start(self, *args: Any, **kwargs: Any) -> None:
        self.tool_calls += 1

    # ── Helpers ────────────────────────────────────────────────────────────────
    @staticmethod
    def _extract_usage(response: Any) -> dict:
        """Return {"input": int, "output": int} from an LLMResult, tolerating
        the OpenAI (``token_usage``), Anthropic (``usage``) and the newer
        ``usage_metadata`` shapes."""
        # 1. llm_output.token_usage / usage  (OpenAI, Anthropic legacy)
        llm_output = getattr(response, "llm_output", None) or {}
        if isinstance(llm_output, dict):
            tu = llm_output.get("token_usage") or llm_output.get("usage") or {}
            if tu:
                return {
                    "input": tu.get("prompt_tokens") or tu.get("input_tokens") or 0,
                    "output": tu.get("completion_tokens") or tu.get("output_tokens") or 0,
                }

        # 2. generations[...].message.usage_metadata  (modern langchain-core)
        try:
            for gen_list in getattr(response, "generations", []) or []:
                for gen in gen_list:
                    message = getattr(gen, "message", None)
                    um = getattr(message, "usage_metadata", None)
                    if um:
                        return {
                            "input": um.get("input_tokens", 0),
                            "output": um.get("output_tokens", 0),
                        }
        except Exception:
            pass
        return {"input": 0, "output": 0}

    def get_stats(self) -> dict:
        return {
            "llm_calls": self.llm_calls,
            "tool_calls": self.tool_calls,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
        }
