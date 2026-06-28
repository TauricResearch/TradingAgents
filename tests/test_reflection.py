"""Tests for the Reflector class (post-trade reflection)."""

from unittest.mock import MagicMock

import pytest

from tradingagents.graph.reflection import Reflector


def _mock_llm(response_text="Reflection output."):
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content=response_text)
    return llm


@pytest.mark.unit
class TestReflector:
    def test_reflect_returns_llm_content(self):
        llm = _mock_llm("The call was correct. Alpha was +2.3%.")
        r = Reflector(llm)
        result = r.reflect_on_final_decision("Buy NVDA", raw_return=0.05, alpha_return=0.023)
        assert result == "The call was correct. Alpha was +2.3%."

    def test_reflect_passes_return_data_to_llm(self):
        llm = _mock_llm()
        r = Reflector(llm)
        r.reflect_on_final_decision("Hold AAPL", raw_return=-0.02, alpha_return=-0.05)
        messages = llm.invoke.call_args[0][0]
        human_msg = messages[1][1]
        assert "-2.0%" in human_msg
        assert "-5.0%" in human_msg

    def test_reflect_passes_final_decision_to_llm(self):
        llm = _mock_llm()
        r = Reflector(llm)
        r.reflect_on_final_decision("Sell TSLA at 250", raw_return=0.1, alpha_return=0.08)
        messages = llm.invoke.call_args[0][0]
        human_msg = messages[1][1]
        assert "Sell TSLA at 250" in human_msg

    def test_reflect_uses_system_prompt(self):
        llm = _mock_llm()
        r = Reflector(llm)
        r.reflect_on_final_decision("Buy", raw_return=0.0, alpha_return=0.0)
        messages = llm.invoke.call_args[0][0]
        system_msg = messages[0][1]
        assert "trading analyst" in system_msg
        assert "2-4 sentences" in system_msg

    def test_custom_benchmark_name(self):
        llm = _mock_llm()
        r = Reflector(llm)
        r.reflect_on_final_decision(
            "Buy 7203.T", raw_return=0.03, alpha_return=0.01, benchmark_name="^N225"
        )
        messages = llm.invoke.call_args[0][0]
        human_msg = messages[1][1]
        assert "^N225" in human_msg

    def test_default_benchmark_is_spy(self):
        llm = _mock_llm()
        r = Reflector(llm)
        r.reflect_on_final_decision("Buy NVDA", raw_return=0.05, alpha_return=0.02)
        messages = llm.invoke.call_args[0][0]
        human_msg = messages[1][1]
        assert "SPY" in human_msg

    def test_log_reflection_prompt_is_deterministic(self):
        llm = _mock_llm()
        r = Reflector(llm)
        assert r.log_reflection_prompt == r._get_log_reflection_prompt()

    def test_positive_return_formatting(self):
        llm = _mock_llm()
        r = Reflector(llm)
        r.reflect_on_final_decision("Buy", raw_return=0.123, alpha_return=0.045)
        messages = llm.invoke.call_args[0][0]
        human_msg = messages[1][1]
        assert "+12.3%" in human_msg
        assert "+4.5%" in human_msg

    def test_negative_return_formatting(self):
        llm = _mock_llm()
        r = Reflector(llm)
        r.reflect_on_final_decision("Sell", raw_return=-0.087, alpha_return=-0.123)
        messages = llm.invoke.call_args[0][0]
        human_msg = messages[1][1]
        assert "-8.7%" in human_msg
        assert "-12.3%" in human_msg
