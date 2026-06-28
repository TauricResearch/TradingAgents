"""Tests for bull and bear researcher agents.

Verifies state mutations, prompt construction, debate history accumulation,
count incrementing, and crypto asset label handling.
"""

from unittest.mock import MagicMock

import pytest

from tradingagents.agents.researchers.bull_researcher import create_bull_researcher
from tradingagents.agents.researchers.bear_researcher import create_bear_researcher


def _make_base_state(
    investment_debate_state=None,
    asset_type="stock",
):
    if investment_debate_state is None:
        investment_debate_state = {
            "bull_history": "",
            "bear_history": "",
            "history": "",
            "current_response": "",
            "judge_decision": "",
            "count": 0,
        }
    return {
        "investment_debate_state": investment_debate_state,
        "market_report": "Bullish technicals.",
        "sentiment_report": "Positive sentiment.",
        "news_report": "Earnings beat expectations.",
        "fundamentals_report": "Revenue up 20% YoY.",
        "company_of_interest": "NVDA",
        "asset_type": asset_type,
    }


def _mock_llm(response_text="Investment argument."):
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content=response_text)
    return llm


# ---------------------------------------------------------------------------
# Bull Researcher
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestBullResearcher:
    def test_returns_investment_debate_state(self):
        node = create_bull_researcher(_mock_llm())
        result = node(_make_base_state())
        assert "investment_debate_state" in result

    def test_increments_count(self):
        node = create_bull_researcher(_mock_llm())
        result = node(_make_base_state())
        assert result["investment_debate_state"]["count"] == 1

    def test_appends_to_bull_history(self):
        llm = _mock_llm("Growth is strong!")
        node = create_bull_researcher(llm)
        result = node(_make_base_state())
        assert "Bull Analyst: Growth is strong!" in result["investment_debate_state"]["bull_history"]

    def test_appends_to_overall_history(self):
        llm = _mock_llm("AI boom is real.")
        node = create_bull_researcher(llm)
        result = node(_make_base_state())
        assert "Bull Analyst: AI boom is real." in result["investment_debate_state"]["history"]

    def test_sets_current_response(self):
        llm = _mock_llm("Buy opportunity!")
        node = create_bull_researcher(llm)
        result = node(_make_base_state())
        assert result["investment_debate_state"]["current_response"] == "Bull Analyst: Buy opportunity!"

    def test_preserves_bear_history(self):
        state = _make_base_state()
        state["investment_debate_state"]["bear_history"] = "Prior bear argument."
        node = create_bull_researcher(_mock_llm())
        result = node(state)
        assert result["investment_debate_state"]["bear_history"] == "Prior bear argument."

    def test_prompt_includes_reports(self):
        llm = _mock_llm()
        node = create_bull_researcher(llm)
        node(_make_base_state())
        prompt = llm.invoke.call_args[0][0]
        assert "Bullish technicals." in prompt
        assert "Positive sentiment." in prompt
        assert "Earnings beat expectations." in prompt
        assert "Revenue up 20% YoY." in prompt

    def test_prompt_includes_bear_response_for_rebuttal(self):
        state = _make_base_state()
        state["investment_debate_state"]["current_response"] = "Bear: Market is overheated."
        llm = _mock_llm()
        node = create_bull_researcher(llm)
        node(state)
        prompt = llm.invoke.call_args[0][0]
        assert "Bear: Market is overheated." in prompt

    def test_stock_asset_type_uses_stock_label(self):
        llm = _mock_llm()
        node = create_bull_researcher(llm)
        node(_make_base_state(asset_type="stock"))
        prompt = llm.invoke.call_args[0][0]
        assert "stock" in prompt
        assert "Company fundamentals report" in prompt

    def test_crypto_asset_type_uses_asset_label(self):
        llm = _mock_llm()
        node = create_bull_researcher(llm)
        node(_make_base_state(asset_type="crypto"))
        prompt = llm.invoke.call_args[0][0]
        assert "asset" in prompt
        assert "may be unavailable for crypto" in prompt


# ---------------------------------------------------------------------------
# Bear Researcher
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestBearResearcher:
    def test_returns_investment_debate_state(self):
        node = create_bear_researcher(_mock_llm())
        result = node(_make_base_state())
        assert "investment_debate_state" in result

    def test_increments_count(self):
        node = create_bear_researcher(_mock_llm())
        result = node(_make_base_state())
        assert result["investment_debate_state"]["count"] == 1

    def test_appends_to_bear_history(self):
        llm = _mock_llm("Overvalued!")
        node = create_bear_researcher(llm)
        result = node(_make_base_state())
        assert "Bear Analyst: Overvalued!" in result["investment_debate_state"]["bear_history"]

    def test_appends_to_overall_history(self):
        llm = _mock_llm("Recession risk.")
        node = create_bear_researcher(llm)
        result = node(_make_base_state())
        assert "Bear Analyst: Recession risk." in result["investment_debate_state"]["history"]

    def test_sets_current_response(self):
        llm = _mock_llm("Sell signal!")
        node = create_bear_researcher(llm)
        result = node(_make_base_state())
        assert result["investment_debate_state"]["current_response"] == "Bear Analyst: Sell signal!"

    def test_preserves_bull_history(self):
        state = _make_base_state()
        state["investment_debate_state"]["bull_history"] = "Prior bull argument."
        node = create_bear_researcher(_mock_llm())
        result = node(state)
        assert result["investment_debate_state"]["bull_history"] == "Prior bull argument."

    def test_prompt_includes_bull_response_for_rebuttal(self):
        state = _make_base_state()
        state["investment_debate_state"]["current_response"] = "Bull: AI spending is accelerating."
        llm = _mock_llm()
        node = create_bear_researcher(llm)
        node(state)
        prompt = llm.invoke.call_args[0][0]
        assert "Bull: AI spending is accelerating." in prompt

    def test_crypto_asset_type_uses_asset_label(self):
        llm = _mock_llm()
        node = create_bear_researcher(llm)
        node(_make_base_state(asset_type="crypto"))
        prompt = llm.invoke.call_args[0][0]
        assert "asset" in prompt
        assert "may be unavailable for crypto" in prompt


# ---------------------------------------------------------------------------
# Bull-Bear Debate Round Trip
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestBullBearDebateRoundTrip:
    def test_two_round_debate(self):
        """Simulate: bull -> bear -> bull -> bear."""
        state = _make_base_state()

        # Round 1: Bull opens
        bull_llm = _mock_llm("Bull round 1.")
        bull_node = create_bull_researcher(bull_llm)
        r1 = bull_node(state)
        assert r1["investment_debate_state"]["count"] == 1
        assert r1["investment_debate_state"]["current_response"].startswith("Bull")

        # Round 1: Bear responds
        state2 = _make_base_state(investment_debate_state=r1["investment_debate_state"])
        bear_llm = _mock_llm("Bear round 1.")
        bear_node = create_bear_researcher(bear_llm)
        r2 = bear_node(state2)
        assert r2["investment_debate_state"]["count"] == 2
        assert r2["investment_debate_state"]["current_response"].startswith("Bear")

        # Round 2: Bull rebuts
        state3 = _make_base_state(investment_debate_state=r2["investment_debate_state"])
        bull_llm2 = _mock_llm("Bull round 2.")
        bull_node2 = create_bull_researcher(bull_llm2)
        r3 = bull_node2(state3)
        assert r3["investment_debate_state"]["count"] == 3

        # Round 2: Bear responds
        state4 = _make_base_state(investment_debate_state=r3["investment_debate_state"])
        bear_llm2 = _mock_llm("Bear round 2.")
        bear_node2 = create_bear_researcher(bear_llm2)
        r4 = bear_node2(state4)
        assert r4["investment_debate_state"]["count"] == 4

        final = r4["investment_debate_state"]
        assert "Bull round 1" in final["bull_history"]
        assert "Bull round 2" in final["bull_history"]
        assert "Bear round 1" in final["bear_history"]
        assert "Bear round 2" in final["bear_history"]
        assert "Bull round 1" in final["history"]
        assert "Bear round 2" in final["history"]
