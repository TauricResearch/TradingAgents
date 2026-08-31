"""The first speaker in each debate must not rebut a nonexistent argument (#1176).

Each debate round's opening speaker receives an empty opponent response; the
prompt used to interpolate it into a "refute the opponent" instruction, so models
fabricated the other side's position. All five debators (bull, bear, and the
three risk analysts) now substitute an explicit opening marker when the opponent
has not spoken, and pass a real argument through unchanged.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tradingagents.agents.researchers.bear_researcher import create_bear_researcher
from tradingagents.agents.researchers.bull_researcher import create_bull_researcher
from tradingagents.agents.risk_mgmt.aggressive_debator import create_aggressive_debator
from tradingagents.agents.risk_mgmt.conservative_debator import create_conservative_debator
from tradingagents.agents.risk_mgmt.neutral_debator import create_neutral_debator
from tradingagents.agents.utils.agent_utils import opponent_argument_or_opening

_REPORTS = {
    "company_of_interest": "AAPL", "asset_type": "stock",
    "market_report": "m", "sentiment_report": "s",
    "news_report": "n", "fundamentals_report": "f",
}


def _capturing_llm(captured: dict):
    llm = MagicMock()
    llm.invoke.side_effect = lambda prompt: (
        captured.__setitem__("prompt", prompt) or MagicMock(content="argument")
    )
    return llm


def _investment_state(current_response):
    return {
        **_REPORTS,
        "count": 0,
        "investment_debate_state": {
            "history": "", "bull_history": "", "bear_history": "",
            "current_response": current_response, "count": 0,
        },
    }


def _risk_state(**responses):
    base = {
        "current_aggressive_response": "", "current_conservative_response": "",
        "current_neutral_response": "", "history": "", "aggressive_history": "",
        "conservative_history": "", "neutral_history": "", "count": 0,
    }
    base.update(responses)
    return {**_REPORTS, "trader_investment_plan": "plan", "risk_debate_state": base}


# --- shared helper ----------------------------------------------------------

@pytest.mark.unit
def test_helper_marks_empty_and_passes_through():
    assert "has not spoken yet" in opponent_argument_or_opening("", "bear analyst")
    assert opponent_argument_or_opening("  real point ", "bear") == "real point"


# --- researchers ------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize(
    "factory,opponent",
    [(create_bull_researcher, "bear"), (create_bear_researcher, "bull")],
)
def test_researcher_opening_has_no_phantom_opponent(factory, opponent):
    captured = {}
    factory(_capturing_llm(captured))(_investment_state(""))
    assert "has not spoken yet" in captured["prompt"]


@pytest.mark.unit
def test_researcher_passes_real_opponent_argument():
    captured = {}
    state = _investment_state("Bear Analyst: valuation is stretched")
    create_bull_researcher(_capturing_llm(captured))(state)
    assert "valuation is stretched" in captured["prompt"]
    assert "has not spoken yet" not in captured["prompt"]


# --- risk debators ----------------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize(
    "factory", [create_aggressive_debator, create_conservative_debator, create_neutral_debator]
)
def test_risk_opening_has_no_phantom_opponent(factory):
    captured = {}
    factory(_capturing_llm(captured))(_risk_state())
    # Both opponent slots were empty -> two opening markers, no fabricated args.
    assert captured["prompt"].count("has not spoken yet") == 2


@pytest.mark.unit
def test_risk_passes_real_opponent_arguments():
    captured = {}
    state = _risk_state(
        current_conservative_response="Conservative Analyst: trim risk",
        current_neutral_response="Neutral Analyst: hold steady",
    )
    create_aggressive_debator(_capturing_llm(captured))(state)
    assert "trim risk" in captured["prompt"]
    assert "hold steady" in captured["prompt"]
    assert "has not spoken yet" not in captured["prompt"]
