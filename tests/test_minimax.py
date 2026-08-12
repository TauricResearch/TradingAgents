"""Tests for MinimaxChatOpenAI quirks.

Verifies the subclass injects ``reasoning_split=True`` into outgoing
requests so MiniMax M-series reasoning models put their <think> block into
``reasoning_details`` instead of polluting ``message.content``.
"""

import os

import pytest
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from tradingagents.llm_clients.openai_client import MinimaxChatOpenAI, OpenAIClient


def _client(model: str = "MiniMax-M2.7", **kwargs):
    os.environ.setdefault("MINIMAX_API_KEY", "placeholder")
    return MinimaxChatOpenAI(
        model=model,
        api_key="placeholder",
        base_url="https://api.minimax.io/v1",
        **kwargs,
    )


@pytest.mark.unit
class TestMinimaxReasoningSplit:
    def test_reasoning_split_sent_via_extra_body_not_top_level(self):
        # Must be in extra_body, not top-level: the openai SDK validates
        # top-level params and rejects unknown ones like reasoning_split (#826).
        payload = _client()._get_request_payload([HumanMessage(content="hi")])
        assert payload.get("extra_body", {}).get("reasoning_split") is True
        assert "reasoning_split" not in payload  # never top-level

    def test_m3_uses_reasoning_split_for_response_formatting(self):
        payload = _client("MiniMax-M3")._get_request_payload([HumanMessage(content="hi")])
        assert payload.get("extra_body", {}).get("reasoning_split") is True
        assert payload.get("extra_body", {}).get("thinking") == {"type": "adaptive"}

    def test_m3_preserves_disabled_thinking_control(self):
        payload = _client(
            "MiniMax-M3", extra_body={"thinking": {"type": "disabled"}}
        )._get_request_payload([HumanMessage(content="hi")])
        assert payload.get("extra_body", {}).get("thinking") == {"type": "disabled"}

    def test_m2_rejects_configurable_thinking(self):
        client = _client(
            "MiniMax-M2.7", extra_body={"thinking": {"type": "disabled"}}
        )
        with pytest.raises(ValueError, match="does not support thinking type"):
            client._get_request_payload([HumanMessage(content="hi")])

    def test_high_level_client_forwards_thinking_control(self):
        client = OpenAIClient(
            model="MiniMax-M3",
            provider="minimax",
            api_key="placeholder",
            extra_body={"thinking": {"type": "disabled"}},
        ).get_llm()
        payload = client._get_request_payload([HumanMessage(content="hi")])
        assert payload.get("extra_body", {}).get("thinking") == {"type": "disabled"}

    def test_non_reasoning_minimax_does_not_inject_reasoning_split(self):
        """Coding Plan / MiniMax-Text-01 / any non-M-series model must NOT
        receive reasoning_split at all (top-level or extra_body) (#826)."""
        for model in ("minimax-text-01", "MiniMax-Coding-Plan"):
            payload = _client(model)._get_request_payload(
                [HumanMessage(content="hi")]
            )
            assert "reasoning_split" not in payload
            assert "reasoning_split" not in payload.get("extra_body", {})


@pytest.mark.unit
class TestMinimaxStructuredOutputDispatch:
    """MiniMax M-series models route through the capability table — tool_choice is
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

    def test_m3_suppresses_tool_choice(self):
        bound = _client("MiniMax-M3").with_structured_output(self._Pick)
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
