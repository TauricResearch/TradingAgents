import threading
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage
from langchain_core.outputs import LLMResult


class TokenCallbackHandler(BaseCallbackHandler):
    """Tracks LLM token usage. Call snapshot_and_reset() after each agent step
    to get the delta tokens consumed by that step, then zero the counters."""

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self._tokens_in = 0
        self._tokens_out = 0

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        try:
            generation = response.generations[0][0]
        except (IndexError, TypeError):
            return
        if not hasattr(generation, "message"):
            return
        message = generation.message
        if not isinstance(message, AIMessage):
            return
        usage = getattr(message, "usage_metadata", None)
        if usage is not None:
            with self._lock:
                self._tokens_in += usage.get("input_tokens", 0)
                self._tokens_out += usage.get("output_tokens", 0)

    def snapshot_and_reset(self) -> dict[str, int]:
        """Return {"in": N, "out": M} for the current period and zero counters."""
        with self._lock:
            result = {"in": self._tokens_in, "out": self._tokens_out}
            self._tokens_in = 0
            self._tokens_out = 0
        return result
