"""Tests for MinimaxChatOpenAI quirks.

Verifies the subclass injects ``reasoning_split=True`` into outgoing
requests so M2.x reasoning models put their <think> block into
``reasoning_details`` instead of polluting ``message.content``.
"""

import os

import pytest
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from tradingagents.llm_clients.capabilities import _MINIMAX_THINKING, get_capabilities
from tradingagents.llm_clients.factory import create_llm_client
from tradingagents.llm_clients.openai_client import MinimaxChatOpenAI, NormalizedChatOpenAI


def _client(model: str = "MiniMax-M2.7"):
    os.environ.setdefault("MINIMAX_API_KEY", "placeholder")
    return MinimaxChatOpenAI(
        model=model,
        api_key="placeholder",
        base_url="https://api.minimax.io/v1",
    )


@pytest.mark.unit
class TestMinimaxReasoningSplit:
    def test_reasoning_split_sent_via_extra_body_not_top_level(self):
        # Must be in extra_body, not top-level: the openai SDK validates
        # top-level params and rejects unknown ones like reasoning_split (#826).
        payload = _client()._get_request_payload([HumanMessage(content="hi")])
        assert payload.get("extra_body", {}).get("reasoning_split") is True
        assert "reasoning_split" not in payload  # never top-level

    def test_non_reasoning_minimax_does_not_inject_reasoning_split(self):
        """Coding Plan / MiniMax-Text-01 / any non-M2-prefixed model must NOT
        receive reasoning_split at all (top-level or extra_body) (#826)."""
        for model in ("minimax-text-01", "MiniMax-Coding-Plan"):
            payload = _client(model)._get_request_payload(
                [HumanMessage(content="hi")]
            )
            assert "reasoning_split" not in payload
            assert "reasoning_split" not in payload.get("extra_body", {})


@pytest.mark.unit
class TestMinimaxStructuredOutputDispatch:
    """M2.x models route through the capability table — tool_choice is
    suppressed but the schema is still bound as a tool."""

    class _Pick(BaseModel):
        action: str

    def _bound_kwargs(self, runnable):
        first = runnable.steps[0] if hasattr(runnable, "steps") else runnable
        return getattr(first, "kwargs", {})

    def test_m2_7_suppresses_tool_choice(self):
        bound = _client("MiniMax-M2.7").with_structured_output(self._Pick)
        kwargs = self._bound_kwargs(bound)
        assert kwargs.get("tool_choice") is None or "tool_choice" not in kwargs

    def test_m2_7_highspeed_suppresses_tool_choice(self):
        bound = _client("MiniMax-M2.7-highspeed").with_structured_output(self._Pick)
        kwargs = self._bound_kwargs(bound)
        assert kwargs.get("tool_choice") is None or "tool_choice" not in kwargs

    def test_schema_still_bound_as_tool(self):
        bound = _client("MiniMax-M2.7").with_structured_output(self._Pick)
        tools = self._bound_kwargs(bound).get("tools", [])
        assert any(
            t.get("function", {}).get("name") == "_Pick" for t in tools
        ), f"schema not bound: {tools}"


@pytest.mark.unit
class TestOpenAICompatibleResponsesApiRouting:
    """Only native OpenAI hosts should enable the Responses API."""

    def _openai_llm(self, monkeypatch, base_url=None):
        monkeypatch.setenv("OPENAI_API_KEY", "test-dummy-not-a-real-key")
        return create_llm_client(
            "openai",
            "gpt-5.4-mini",
            base_url=base_url,
        ).get_llm()

    def test_openai_provider_without_base_url_uses_responses_api(self, monkeypatch):
        llm = self._openai_llm(monkeypatch)

        assert llm.use_responses_api is True

    def test_openai_provider_with_native_openai_base_url_uses_responses_api(self, monkeypatch):
        llm = self._openai_llm(monkeypatch, "https://api.openai.com/v1")

        assert llm.use_responses_api is True

    def test_openai_provider_with_nvidia_base_url_uses_chat_completions(self, monkeypatch):
        llm = self._openai_llm(monkeypatch, "https://integrate.api.nvidia.com/v1")

        assert isinstance(llm, NormalizedChatOpenAI)
        assert llm.use_responses_api is False


@pytest.mark.unit
class TestNvidiaHostedMinimaxCapabilities:
    def test_nvidia_hosted_minimax_m2_7_uses_minimax_thinking_capabilities(self):
        assert get_capabilities("minimaxai/minimax-m2.7") == _MINIMAX_THINKING
