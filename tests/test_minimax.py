"""Tests for MinimaxChatOpenAI quirks.

Verifies the subclass injects ``reasoning_split=True`` under ``extra_body``
in the request payload for M2.x reasoning models. This ensures the
parameter reaches the MiniMax API without triggering the OpenAI SDK's
strict kwarg validation on ``Completions.create()`` (see #826).
"""

import os

import pytest
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from tradingagents.llm_clients.openai_client import MinimaxChatOpenAI


def _client(model: str = "MiniMax-M2.7"):
    os.environ.setdefault("MINIMAX_API_KEY", "placeholder")
    return MinimaxChatOpenAI(
        model=model,
        api_key="placeholder",
        base_url="https://api.minimax.io/v1",
    )


@pytest.mark.unit
class TestMinimaxReasoningSplit:
    def test_request_payload_sets_reasoning_split_under_extra_body(self):
        """reasoning_split must be nested under extra_body.

        Top-level keys are unpacked as kwargs to the OpenAI SDK's
        Completions.create(), which rejects unknown parameters with
        TypeError. Only extra_body is forwarded into the request body.
        """
        payload = _client()._get_request_payload([HumanMessage(content="hi")])
        assert payload.get("reasoning_split") is None  # never at top level
        extra_body = payload.get("extra_body") or {}
        assert extra_body.get("reasoning_split") is True

    def test_caller_supplied_reasoning_split_in_extra_body_is_preserved(self):
        """Caller-provided value inside extra_body is left untouched."""
        client = _client()
        payload = client._get_request_payload(
            [HumanMessage(content="hi")],
            extra_body={"reasoning_split": False, "other": 1},
        )
        extra_body = payload.get("extra_body") or {}
        assert extra_body.get("reasoning_split") is False
        assert extra_body.get("other") == 1  # other keys preserved

    def test_non_reasoning_minimax_does_not_inject_reasoning_split(self):
        """Coding Plan / MiniMax-Text-01 / any non-M2-prefixed model must NOT
        receive reasoning_split — the openai SDK rejects unknown kwargs with
        TypeError (#826)."""
        for model in ("minimax-text-01", "MiniMax-Coding-Plan"):
            payload = _client(model)._get_request_payload(
                [HumanMessage(content="hi")]
            )
            # Must not appear at top level
            assert "reasoning_split" not in payload, (
                f"{model!r} payload unexpectedly contains top-level reasoning_split"
            )
            # Must not appear under extra_body either
            eb = payload.get("extra_body") or {}
            assert eb.get("reasoning_split") is None, (
                f"{model!r} extra_body unexpectedly contains reasoning_split"
            )

    def test_merges_into_existing_extra_body_without_clobber(self):
        """When extra_body already exists (e.g. from model_kwargs), we add
        our key without removing other entries."""
        # Simulate a client that was constructed with extra_body already set
        # (users can do this via model_kwargs or direct kwarg in some paths).
        os.environ.setdefault("MINIMAX_API_KEY", "placeholder")
        client = MinimaxChatOpenAI(
            model="MiniMax-M2.7",
            api_key="placeholder",
            base_url="https://api.minimax.io/v1",
            extra_body={"ttl": 300},  # user-provided custom param
        )
        payload = client._get_request_payload([HumanMessage(content="hi")])
        eb = payload.get("extra_body") or {}
        assert eb.get("reasoning_split") is True
        assert eb.get("ttl") == 300  # original user value kept


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
