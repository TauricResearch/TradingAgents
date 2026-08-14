"""Debate opening statements must not prompt a rebuttal of a nonexistent argument.

Regressions for #1176: the first speaker in each debate receives an empty
``current_response`` (or empty opponent responses) yet the prompt demands it
rebut the other side -- so models fabricate the opponent's position. Opening
speakers now get an explicit "present your own case" instruction instead of a
rebuttal framing.
"""

from unittest.mock import MagicMock

import pytest

from tradingagents.agents.researchers.bear_researcher import create_bear_researcher
from tradingagents.agents.researchers.bull_researcher import create_bull_researcher
from tradingagents.agents.risk_mgmt.aggressive_debator import create_aggressive_debator
from tradingagents.agents.risk_mgmt.conservative_debator import create_conservative_debator
from tradingagents.agents.risk_mgmt.neutral_debator import create_neutral_debator


def _captured_prompt(factory, state) -> str:
    """Run one agent node with a fake LLM and return the prompt it received."""
    llm = MagicMock()
    response = MagicMock()
    response.content = "argument"
    llm.invoke.return_value = response
    factory(llm)(state)
    return llm.invoke.call_args.args[0]


def _investment_state(current_response: str) -> dict:
    return {
        "company_of_interest": "NVDA",
        "asset_type": "stock",
        "market_report": "market",
        "sentiment_report": "sentiment",
        "news_report": "news",
        "fundamentals_report": "fundamentals",
        "investment_debate_state": {
            "history": "",
            "bull_history": "",
            "bear_history": "",
            "current_response": current_response,
            "count": 0,
        },
    }


def _risk_state(aggressive: str = "", conservative: str = "", neutral: str = "") -> dict:
    return {
        "company_of_interest": "NVDA",
        "asset_type": "stock",
        "market_report": "market",
        "sentiment_report": "sentiment",
        "news_report": "news",
        "fundamentals_report": "fundamentals",
        "trader_investment_plan": "trader plan",
        "risk_debate_state": {
            "history": "",
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
            "current_aggressive_response": aggressive,
            "current_conservative_response": conservative,
            "current_neutral_response": neutral,
            "count": 0,
        },
    }


# ---------------------------------------------------------------------------
# Bull / Bear researchers
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_bull_opening_does_not_reference_bear_argument():
    prompt = _captured_prompt(create_bull_researcher, _investment_state(current_response=""))
    assert "has not spoken yet" in prompt
    assert "Last bear argument:" not in prompt
    assert "rebut any bear argument" in prompt


@pytest.mark.unit
def test_bull_rebuttal_keeps_real_bear_argument():
    prompt = _captured_prompt(
        create_bull_researcher,
        _investment_state(current_response="Bear Analyst: rates are too high"),
    )
    assert "Last bear argument: Bear Analyst: rates are too high" in prompt
    assert "has not spoken yet" not in prompt


@pytest.mark.unit
def test_bear_opening_does_not_reference_bull_argument():
    prompt = _captured_prompt(create_bear_researcher, _investment_state(current_response=""))
    assert "has not spoken yet" in prompt
    assert "Last bull argument:" not in prompt
    assert "rebut any bull argument" in prompt


@pytest.mark.unit
def test_bear_rebuttal_keeps_real_bull_argument():
    prompt = _captured_prompt(
        create_bear_researcher,
        _investment_state(current_response="Bull Analyst: AI demand is exploding"),
    )
    assert "Last bull argument: Bull Analyst: AI demand is exploding" in prompt
    assert "has not spoken yet" not in prompt


# ---------------------------------------------------------------------------
# Risk debate (Aggressive / Conservative / Neutral)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_aggressive_opening_does_not_quote_others():
    prompt = _captured_prompt(create_aggressive_debator, _risk_state())
    assert "not spoken yet" in prompt
    assert "last arguments from the conservative analyst:" not in prompt.lower()
    assert "last arguments from the neutral analyst:" not in prompt.lower()


@pytest.mark.unit
def test_aggressive_rebuttal_quotes_spoken_analysts_only():
    prompt = _captured_prompt(
        create_aggressive_debator,
        _risk_state(conservative="Conservative Analyst: too risky"),
    )
    assert "Conservative Analyst: too risky" in prompt
    assert "has not spoken yet" not in prompt


@pytest.mark.unit
def test_conservative_opening_does_not_quote_others():
    prompt = _captured_prompt(create_conservative_debator, _risk_state())
    assert "not spoken yet" in prompt
    assert "last arguments from the aggressive analyst:" not in prompt.lower()
    assert "last arguments from the neutral analyst:" not in prompt.lower()


@pytest.mark.unit
def test_neutral_opening_does_not_quote_others():
    prompt = _captured_prompt(create_neutral_debator, _risk_state())
    assert "not spoken yet" in prompt
    assert "last arguments from the aggressive analyst:" not in prompt.lower()
    assert "last arguments from the conservative analyst:" not in prompt.lower()


@pytest.mark.unit
def test_neutral_rebuttal_quotes_spoken_analysts_only():
    prompt = _captured_prompt(
        create_neutral_debator,
        _risk_state(aggressive="Aggressive Analyst: go all in"),
    )
    assert "Aggressive Analyst: go all in" in prompt
    assert "has not spoken yet" not in prompt
