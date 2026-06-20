"""Local OpenAI-compatible servers must not receive object-form tool_choice.

LM Studio, llama.cpp, older vLLM, and Ollama implement the Chat Completions
API but reject the function-spec *object* that langchain's ``function_calling``
structured-output path sends as ``tool_choice`` by default, returning::

    400 Invalid tool_choice type: 'object'.
        Supported string values: none, auto, required

(issue #1057). These servers run arbitrary, user-named models, so the
per-model capability table (which keys off the model name) can never catch
them. Suppression therefore has to key off the *provider/endpoint* being a
local/generic OpenAI-compatible server, not the model name.

The schema is still bound as a tool — exactly the DeepSeek/MiniMax pattern
already used for cloud models that reject tool_choice — so structured output
keeps working, just without the rejected parameter.
"""

import os

import pytest
from pydantic import BaseModel

from tradingagents.llm_clients.openai_client import OpenAIClient


def _bound_kwargs(runnable):
    """Extract bind() kwargs from a with_structured_output result.

    Mirrors the helper in test_deepseek_reasoning.py.
    """
    first = runnable.steps[0] if hasattr(runnable, "steps") else runnable
    return getattr(first, "kwargs", {})


def _tool_choice_suppressed(kwargs) -> bool:
    """A suppressed tool_choice is either absent or explicitly None — both
    signal that langchain's bind_tools will skip the parameter on the wire."""
    return kwargs.get("tool_choice") is None or "tool_choice" not in kwargs


class _Sample(BaseModel):
    answer: str


@pytest.mark.unit
class TestLocalServerToolChoiceSuppression:
    def _structured(self, **client_kwargs):
        llm = OpenAIClient(**client_kwargs).get_llm()
        return llm.with_structured_output(_Sample)

    def test_openai_compatible_endpoint_suppresses_tool_choice(self):
        """The generic local endpoint (vLLM / LM Studio via backend_url)
        must not send the object-form tool_choice."""
        bound = self._structured(
            model="some-local-model",
            provider="openai_compatible",
            base_url="http://localhost:1234/v1",
        )
        assert _tool_choice_suppressed(_bound_kwargs(bound))

    def test_ollama_endpoint_suppresses_tool_choice(self):
        bound = self._structured(model="qwen2.5", provider="ollama")
        assert _tool_choice_suppressed(_bound_kwargs(bound))

    def test_schema_is_still_bound_as_tool(self):
        """Suppressing tool_choice must not drop the schema: it still ships
        as a tool so structured output keeps working."""
        bound = self._structured(
            model="some-local-model",
            provider="openai_compatible",
            base_url="http://localhost:1234/v1",
        )
        tools = _bound_kwargs(bound).get("tools", [])
        assert any(
            t.get("function", {}).get("name") == "_Sample" for t in tools
        ), f"schema not bound as a tool: {tools}"

    def test_hosted_provider_still_sends_tool_choice(self, monkeypatch):
        """Suppression must not leak to hosted OpenAI-compatible providers
        (e.g. xAI) that accept the object-form tool_choice."""
        monkeypatch.setenv("XAI_API_KEY", "placeholder")
        bound = self._structured(model="grok-2", provider="xai")
        assert _bound_kwargs(bound).get("tool_choice") is not None
