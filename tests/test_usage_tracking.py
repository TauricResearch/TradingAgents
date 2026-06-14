"""Usage tracking aggregates token/call counts and (optionally) estimates cost."""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from tradingagents.usage import UsageTrackingCallback


def _llm_result(input_tokens: int, output_tokens: int) -> LLMResult:
    msg = AIMessage(
        content="ok",
        usage_metadata={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
    )
    return LLMResult(generations=[[ChatGeneration(message=msg)]])


@pytest.mark.unit
def test_aggregates_calls_and_tokens():
    cb = UsageTrackingCallback()
    cb.on_chat_model_start({}, [[]])
    cb.on_llm_end(_llm_result(100, 50))
    cb.on_chat_model_start({}, [[]])
    cb.on_llm_end(_llm_result(200, 25))
    cb.on_tool_start({}, "input")

    s = cb.summary()
    assert s["llm_calls"] == 2
    assert s["tool_calls"] == 1
    assert s["tokens_in"] == 300
    assert s["tokens_out"] == 75
    assert s["tokens_total"] == 375


@pytest.mark.unit
def test_cost_none_without_prices():
    cb = UsageTrackingCallback()
    cb.on_llm_end(_llm_result(1000, 1000))
    assert cb.estimated_cost_usd() is None
    assert "set config['model_prices']" in cb.format_summary()


@pytest.mark.unit
def test_cost_estimate_with_prices():
    # $0.30 / 1M input, $1.20 / 1M output
    cb = UsageTrackingCallback(model_prices={"input": 0.30, "output": 1.20})
    cb.on_llm_end(_llm_result(1_000_000, 500_000))
    # 1M * 0.30 + 0.5M * 1.20 = 0.30 + 0.60 = 0.90
    assert cb.estimated_cost_usd() == pytest.approx(0.90)
    assert "est. cost $0.9000" in cb.format_summary()


@pytest.mark.unit
def test_malformed_response_is_ignored():
    cb = UsageTrackingCallback()
    cb.on_llm_end(LLMResult(generations=[[]]))  # no generations -> no crash
    assert cb.summary()["tokens_total"] == 0


@pytest.mark.unit
def test_cli_handler_is_a_usage_tracker():
    """The CLI handler subclasses the library tracker and keeps get_stats()."""
    from cli.stats_handler import StatsCallbackHandler

    cb = StatsCallbackHandler()
    assert isinstance(cb, UsageTrackingCallback)
    cb.on_chat_model_start({}, [[]])
    cb.on_llm_end(_llm_result(10, 5))
    stats = cb.get_stats()
    assert stats == {"llm_calls": 1, "tool_calls": 0, "tokens_in": 10, "tokens_out": 5}
