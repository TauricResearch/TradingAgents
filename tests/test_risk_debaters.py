"""Tests for risk management debater agents (aggressive, conservative, neutral).

Verifies state mutations, prompt construction, debate history accumulation,
and count incrementing — the core contract each debater must uphold.
"""

from unittest.mock import MagicMock

import pytest

from tradingagents.agents.risk_mgmt.aggressive_debator import create_aggressive_debator
from tradingagents.agents.risk_mgmt.conservative_debator import create_conservative_debator
from tradingagents.agents.risk_mgmt.neutral_debator import create_neutral_debator


def _make_base_state(
    risk_debate_state=None,
    trader_decision="Buy NVDA at 189.50",
):
    if risk_debate_state is None:
        risk_debate_state = {
            "history": "",
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
            "latest_speaker": "",
            "current_aggressive_response": "",
            "current_conservative_response": "",
            "current_neutral_response": "",
            "count": 0,
        }
    return {
        "risk_debate_state": risk_debate_state,
        "market_report": "Market is bullish.",
        "sentiment_report": "Sentiment is positive.",
        "news_report": "No major news.",
        "fundamentals_report": "Strong earnings.",
        "trader_investment_plan": trader_decision,
        "company_of_interest": "NVDA",
        "asset_type": "stock",
    }


def _mock_llm(response_text="This is my argument."):
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content=response_text)
    return llm


# ---------------------------------------------------------------------------
# Aggressive Debater
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestAggressiveDebator:
    def test_returns_risk_debate_state(self):
        llm = _mock_llm("High risk, high reward!")
        node = create_aggressive_debator(llm)
        result = node(_make_base_state())
        assert "risk_debate_state" in result

    def test_increments_count(self):
        llm = _mock_llm()
        node = create_aggressive_debator(llm)
        result = node(_make_base_state())
        assert result["risk_debate_state"]["count"] == 1

    def test_sets_latest_speaker(self):
        llm = _mock_llm()
        node = create_aggressive_debator(llm)
        result = node(_make_base_state())
        assert result["risk_debate_state"]["latest_speaker"] == "Aggressive"

    def test_appends_to_aggressive_history(self):
        llm = _mock_llm("Risk is opportunity!")
        node = create_aggressive_debator(llm)
        result = node(_make_base_state())
        assert "Aggressive Analyst: Risk is opportunity!" in result["risk_debate_state"]["aggressive_history"]

    def test_appends_to_overall_history(self):
        llm = _mock_llm("Go big or go home!")
        node = create_aggressive_debator(llm)
        result = node(_make_base_state())
        assert "Aggressive Analyst: Go big or go home!" in result["risk_debate_state"]["history"]

    def test_sets_current_aggressive_response(self):
        llm = _mock_llm("Bold move!")
        node = create_aggressive_debator(llm)
        result = node(_make_base_state())
        assert result["risk_debate_state"]["current_aggressive_response"] == "Aggressive Analyst: Bold move!"

    def test_preserves_other_histories(self):
        state = _make_base_state()
        state["risk_debate_state"]["conservative_history"] = "Prior conservative arg."
        state["risk_debate_state"]["neutral_history"] = "Prior neutral arg."
        llm = _mock_llm()
        node = create_aggressive_debator(llm)
        result = node(state)
        assert result["risk_debate_state"]["conservative_history"] == "Prior conservative arg."
        assert result["risk_debate_state"]["neutral_history"] == "Prior neutral arg."

    def test_preserves_other_current_responses(self):
        state = _make_base_state()
        state["risk_debate_state"]["current_conservative_response"] = "Be careful."
        state["risk_debate_state"]["current_neutral_response"] = "Balance is key."
        llm = _mock_llm()
        node = create_aggressive_debator(llm)
        result = node(state)
        assert result["risk_debate_state"]["current_conservative_response"] == "Be careful."
        assert result["risk_debate_state"]["current_neutral_response"] == "Balance is key."

    def test_prompt_includes_trader_decision(self):
        llm = _mock_llm()
        node = create_aggressive_debator(llm)
        node(_make_base_state(trader_decision="Sell AAPL at 150"))
        prompt = llm.invoke.call_args[0][0]
        assert "Sell AAPL at 150" in prompt

    def test_prompt_includes_reports(self):
        llm = _mock_llm()
        node = create_aggressive_debator(llm)
        node(_make_base_state())
        prompt = llm.invoke.call_args[0][0]
        assert "Market is bullish." in prompt
        assert "Sentiment is positive." in prompt
        assert "No major news." in prompt
        assert "Strong earnings." in prompt

    def test_multi_round_accumulation(self):
        llm = _mock_llm("Round 1 aggressive")
        node = create_aggressive_debator(llm)
        result1 = node(_make_base_state())

        state2 = _make_base_state(risk_debate_state=result1["risk_debate_state"])
        llm2 = _mock_llm("Round 2 aggressive")
        node2 = create_aggressive_debator(llm2)
        result2 = node2(state2)

        assert result2["risk_debate_state"]["count"] == 2
        assert "Round 1 aggressive" in result2["risk_debate_state"]["aggressive_history"]
        assert "Round 2 aggressive" in result2["risk_debate_state"]["aggressive_history"]


# ---------------------------------------------------------------------------
# Conservative Debater
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestConservativeDebator:
    def test_returns_risk_debate_state(self):
        node = create_conservative_debator(_mock_llm())
        result = node(_make_base_state())
        assert "risk_debate_state" in result

    def test_increments_count(self):
        node = create_conservative_debator(_mock_llm())
        result = node(_make_base_state())
        assert result["risk_debate_state"]["count"] == 1

    def test_sets_latest_speaker(self):
        node = create_conservative_debator(_mock_llm())
        result = node(_make_base_state())
        assert result["risk_debate_state"]["latest_speaker"] == "Conservative"

    def test_appends_to_conservative_history(self):
        llm = _mock_llm("Safety first!")
        node = create_conservative_debator(llm)
        result = node(_make_base_state())
        assert "Conservative Analyst: Safety first!" in result["risk_debate_state"]["conservative_history"]

    def test_sets_current_conservative_response(self):
        llm = _mock_llm("Protect capital!")
        node = create_conservative_debator(llm)
        result = node(_make_base_state())
        assert result["risk_debate_state"]["current_conservative_response"] == "Conservative Analyst: Protect capital!"

    def test_preserves_other_histories(self):
        state = _make_base_state()
        state["risk_debate_state"]["aggressive_history"] = "Prior aggressive arg."
        state["risk_debate_state"]["neutral_history"] = "Prior neutral arg."
        node = create_conservative_debator(_mock_llm())
        result = node(state)
        assert result["risk_debate_state"]["aggressive_history"] == "Prior aggressive arg."
        assert result["risk_debate_state"]["neutral_history"] == "Prior neutral arg."

    def test_prompt_includes_aggressive_and_neutral_responses(self):
        state = _make_base_state()
        state["risk_debate_state"]["current_aggressive_response"] = "Go all in!"
        state["risk_debate_state"]["current_neutral_response"] = "Moderate approach."
        llm = _mock_llm()
        node = create_conservative_debator(llm)
        node(state)
        prompt = llm.invoke.call_args[0][0]
        assert "Go all in!" in prompt
        assert "Moderate approach." in prompt


# ---------------------------------------------------------------------------
# Neutral Debater
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestNeutralDebator:
    def test_returns_risk_debate_state(self):
        node = create_neutral_debator(_mock_llm())
        result = node(_make_base_state())
        assert "risk_debate_state" in result

    def test_increments_count(self):
        node = create_neutral_debator(_mock_llm())
        result = node(_make_base_state())
        assert result["risk_debate_state"]["count"] == 1

    def test_sets_latest_speaker(self):
        node = create_neutral_debator(_mock_llm())
        result = node(_make_base_state())
        assert result["risk_debate_state"]["latest_speaker"] == "Neutral"

    def test_appends_to_neutral_history(self):
        llm = _mock_llm("Balanced view.")
        node = create_neutral_debator(llm)
        result = node(_make_base_state())
        assert "Neutral Analyst: Balanced view." in result["risk_debate_state"]["neutral_history"]

    def test_sets_current_neutral_response(self):
        llm = _mock_llm("Consider both sides.")
        node = create_neutral_debator(llm)
        result = node(_make_base_state())
        assert result["risk_debate_state"]["current_neutral_response"] == "Neutral Analyst: Consider both sides."

    def test_preserves_other_histories(self):
        state = _make_base_state()
        state["risk_debate_state"]["aggressive_history"] = "Prior aggressive."
        state["risk_debate_state"]["conservative_history"] = "Prior conservative."
        node = create_neutral_debator(_mock_llm())
        result = node(state)
        assert result["risk_debate_state"]["aggressive_history"] == "Prior aggressive."
        assert result["risk_debate_state"]["conservative_history"] == "Prior conservative."

    def test_prompt_includes_aggressive_and_conservative_responses(self):
        state = _make_base_state()
        state["risk_debate_state"]["current_aggressive_response"] = "Go big!"
        state["risk_debate_state"]["current_conservative_response"] = "Stay safe!"
        llm = _mock_llm()
        node = create_neutral_debator(llm)
        node(state)
        prompt = llm.invoke.call_args[0][0]
        assert "Go big!" in prompt
        assert "Stay safe!" in prompt


# ---------------------------------------------------------------------------
# Cross-debater interaction
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestDebateRoundTrip:
    def test_three_way_debate_round(self):
        """Simulate a full round: aggressive -> conservative -> neutral."""
        state = _make_base_state()

        agg_llm = _mock_llm("Aggressive opening.")
        agg_node = create_aggressive_debator(agg_llm)
        r1 = agg_node(state)
        assert r1["risk_debate_state"]["count"] == 1
        assert r1["risk_debate_state"]["latest_speaker"] == "Aggressive"

        state2 = _make_base_state(risk_debate_state=r1["risk_debate_state"])
        con_llm = _mock_llm("Conservative rebuttal.")
        con_node = create_conservative_debator(con_llm)
        r2 = con_node(state2)
        assert r2["risk_debate_state"]["count"] == 2
        assert r2["risk_debate_state"]["latest_speaker"] == "Conservative"

        state3 = _make_base_state(risk_debate_state=r2["risk_debate_state"])
        neu_llm = _mock_llm("Neutral synthesis.")
        neu_node = create_neutral_debator(neu_llm)
        r3 = neu_node(state3)
        assert r3["risk_debate_state"]["count"] == 3
        assert r3["risk_debate_state"]["latest_speaker"] == "Neutral"

        final = r3["risk_debate_state"]
        assert "Aggressive opening" in final["history"]
        assert "Conservative rebuttal" in final["history"]
        assert "Neutral synthesis" in final["history"]
        assert "Aggressive opening" in final["aggressive_history"]
        assert "Conservative rebuttal" in final["conservative_history"]
        assert "Neutral synthesis" in final["neutral_history"]
