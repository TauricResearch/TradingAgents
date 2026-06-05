"""LLM seam for the brain.

``StructuredLLM`` is the interface the nodes use: given a system prompt + a
context string + an output schema, return a typed Pydantic instance. This keeps
the graph testable offline (inject a fake). ``ForkStructuredLLM`` is the real
adapter over the kept ``llm_clients`` infra (OpenRouter / DeepSeek), reusing the
provider's native structured-output mode.
"""

from __future__ import annotations

from typing import Any, Optional, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@runtime_checkable
class StructuredLLM(Protocol):
    def generate(self, system_prompt: str, context: str, schema: type[T]) -> T: ...


class ForkStructuredLLM:
    """Real structured LLM backed by tradingagents.llm_clients.

    Defaults to the project's provider/model from DEFAULT_CONFIG (set
    ``TRADINGAGENTS_LLM_PROVIDER=openrouter`` + the DeepSeek model in .env).
    Network-bound: used in integration, not unit tests.
    """

    def __init__(self, config: Optional[dict[str, Any]] = None, *, deep: bool = True):
        from ..default_config import DEFAULT_CONFIG
        from ..llm_clients import create_llm_client

        self.config = config or DEFAULT_CONFIG
        model = self.config["deep_think_llm"] if deep else self.config["quick_think_llm"]
        self._llm = create_llm_client(
            self.config["llm_provider"], model, self.config.get("backend_url")
        )

    def generate(self, system_prompt: str, context: str, schema: type[T]) -> T:
        bound = self._llm.with_structured_output(schema)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context},
        ]
        return bound.invoke(messages)
