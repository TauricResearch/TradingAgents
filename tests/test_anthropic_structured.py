"""Tests for Anthropic structured-output method selection.

Forced tool calling (langchain-anthropic's default) is rejected by Opus 5.5,
Sonnet 5.5 and Fable 5.1 and is optional on every thinking-enabled model, so
the Portfolio Manager, Trader, Research Manager and Sentiment Analyst all fell
back to a second, free-text call. Models with native structured outputs bind
``output_config.format`` instead.
"""

import pytest
from pydantic import BaseModel

from tradingagents.llm_clients.anthropic_client import NormalizedChatAnthropic


class _Pick(BaseModel):
    ticker: str
    score: float


def _bound_kwargs(model: str, **kwargs) -> dict:
    llm = NormalizedChatAnthropic(model=model, api_key="x")
    return llm.with_structured_output(_Pick, **kwargs).steps[0].kwargs


@pytest.mark.unit
class TestStructuredMethod:
    @pytest.mark.parametrize(
        "model",
        [
            "claude-opus-5-5",
            "claude-sonnet-5-5",
            "claude-haiku-5-5",
            "claude-fable-5-1",
            "claude-mythos-5-1",
            "claude-opus-5",
            "claude-sonnet-5",
            "claude-opus-4-8",
            "claude-haiku-4-5",
            "claude-haiku-4-5-20251001",
            "claude-opus-4-1",
        ],
    )
    def test_supported_models_use_json_schema(self, model):
        kwargs = _bound_kwargs(model)
        assert kwargs["output_config"]["format"]["type"] == "json_schema"
        assert "tool_choice" not in kwargs

    @pytest.mark.parametrize(
        "model",
        [
            "claude-opus-4-6",
            "claude-opus-4-7",
            "claude-sonnet-4-6",
            "claude-sonnet-4-5",
            "claude-opus-4-20250514",
            "claude-experimental-x",
        ],
    )
    def test_other_models_keep_tool_calling(self, model):
        kwargs = _bound_kwargs(model)
        assert "output_config" not in kwargs
        assert kwargs["tools"][0]["name"] == "_Pick"

    def test_explicit_method_wins(self):
        kwargs = _bound_kwargs("claude-opus-5-5", method="function_calling")
        assert "output_config" not in kwargs
