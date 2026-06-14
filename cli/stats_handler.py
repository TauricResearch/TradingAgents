import threading
from typing import Any, Dict, List, Optional
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from langchain_core.messages import AIMessage


class StatsCallbackHandler(BaseCallbackHandler):
    """Callback handler that tracks LLM calls, tool calls, and token usage.

    Maintains both aggregate totals and a per-model breakdown so consumers
    can attribute cost accurately when a single graph mixes multiple models
    (TradingAgents typically runs a "deep" and a "quick" model alongside
    each other). The breakdown is keyed on the model id reported by
    LangChain — usually the same string passed to the constructor (e.g.
    ``claude-opus-4-6`` or ``gpt-5.4-mini``).
    """

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self.llm_calls = 0
        self.tool_calls = 0
        self.tokens_in = 0
        self.tokens_out = 0
        # Per-model accumulator. Shape: {model_id: {llm_calls, tokens_in, tokens_out}}.
        self.by_model: Dict[str, Dict[str, int]] = {}
        # run_id → model_name, populated on start, consumed on end.
        # Without this we'd have nowhere to look the model up at end time —
        # ``on_llm_end`` doesn't receive ``serialized``.
        self._run_models: Dict[Any, str] = {}

    @staticmethod
    def _model_name(
        serialized: Optional[Dict[str, Any]], kwargs: Dict[str, Any]
    ) -> str:
        """Best-effort model id extraction across LangChain provider quirks.

        LangChain stashes the model under different keys depending on the
        chat-model class. We walk a small priority list and fall through
        to "unknown" rather than raising — token counting must keep working
        even if the upstream library reshapes its kwargs.
        """
        invocation = kwargs.get("invocation_params") or {}
        for key in ("model", "model_name", "model_id"):
            value = invocation.get(key)
            if value:
                return str(value)
        sk = (serialized or {}).get("kwargs") or {}
        for key in ("model", "model_name"):
            value = sk.get(key)
            if value:
                return str(value)
        sid = (serialized or {}).get("id") or []
        if sid:
            return str(sid[-1])
        return "unknown"

    def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: List[str],
        *,
        run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Increment LLM call counter when an LLM starts."""
        with self._lock:
            self.llm_calls += 1
            if run_id is not None:
                self._run_models[run_id] = self._model_name(serialized, kwargs)

    def on_chat_model_start(
        self,
        serialized: Dict[str, Any],
        messages: List[List[Any]],
        *,
        run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Increment LLM call counter when a chat model starts."""
        with self._lock:
            self.llm_calls += 1
            if run_id is not None:
                self._run_models[run_id] = self._model_name(serialized, kwargs)

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Extract token usage from LLM response."""
        try:
            generation = response.generations[0][0]
        except (IndexError, TypeError):
            return

        usage_metadata = None
        if hasattr(generation, "message"):
            message = generation.message
            if isinstance(message, AIMessage) and hasattr(message, "usage_metadata"):
                usage_metadata = message.usage_metadata

        if not usage_metadata:
            return

        in_tok = int(usage_metadata.get("input_tokens", 0) or 0)
        out_tok = int(usage_metadata.get("output_tokens", 0) or 0)

        with self._lock:
            self.tokens_in += in_tok
            self.tokens_out += out_tok

            model = self._run_models.pop(run_id, None) if run_id is not None else None
            # llm_output is sometimes populated even when serialized wasn't —
            # use it as a secondary lookup before falling back to "unknown".
            if not model:
                llm_output = getattr(response, "llm_output", None) or {}
                model = llm_output.get("model_name") or llm_output.get("model")
            if not model:
                model = "unknown"

            entry = self.by_model.setdefault(
                model, {"llm_calls": 0, "tokens_in": 0, "tokens_out": 0}
            )
            entry["llm_calls"] += 1
            entry["tokens_in"] += in_tok
            entry["tokens_out"] += out_tok

    def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        **kwargs: Any,
    ) -> None:
        """Increment tool call counter when a tool starts."""
        with self._lock:
            self.tool_calls += 1

    def get_stats(self) -> Dict[str, Any]:
        """Return current statistics."""
        with self._lock:
            return {
                "llm_calls": self.llm_calls,
                "tool_calls": self.tool_calls,
                "tokens_in": self.tokens_in,
                "tokens_out": self.tokens_out,
                "by_model": {k: dict(v) for k, v in self.by_model.items()},
            }
