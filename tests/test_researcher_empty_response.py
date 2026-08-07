"""The debate opener must not be handed an empty opponent argument (#1176).

`current_response` starts as `""`, and the graph fixes a speaking order, so
whichever researcher runs first used to receive a bare ``Last bear argument:``
(or ``Last bull argument:``) with nothing after it — which the model reads as
an argument it should rebut, and fabricates one to rebut.

These assert against the *rendered* prompt each researcher actually sends.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tradingagents.agents.researchers.bear_researcher import create_bear_researcher
from tradingagents.agents.researchers.bull_researcher import create_bull_researcher


def _capturing_llm(captured: dict):
    llm = MagicMock()
    llm.invoke.side_effect = lambda prompt: (
        captured.__setitem__("prompt", prompt) or MagicMock(content="argument text")
    )
    return llm


def _state(current_response: str, count: int) -> dict:
    return {
        "company_of_interest": "NVDA",
        "market_report": "market",
        "sentiment_report": "sentiment",
        "news_report": "news",
        "fundamentals_report": "fundamentals",
        "investment_debate_state": {
            "history": "" if count == 0 else "prior turns",
            "bull_history": "",
            "bear_history": "",
            "current_response": current_response,
            "judge_decision": "",
            "count": count,
        },
    }


@pytest.mark.unit
def test_bull_opening_turn_omits_empty_bear_argument():
    captured = {}
    create_bull_researcher(_capturing_llm(captured))(_state("", 0))
    prompt = captured["prompt"]
    assert "Last bear argument:" not in prompt
    assert "no responses from the bear analyst yet" in prompt


@pytest.mark.unit
def test_bear_opening_turn_omits_empty_bull_argument():
    # Reachable by reversing the debate order, or from a state built without a
    # prior bull turn; the guard must not depend on who the graph runs first.
    captured = {}
    create_bear_researcher(_capturing_llm(captured))(_state("", 0))
    prompt = captured["prompt"]
    assert "Last bull argument:" not in prompt
    assert "no responses from the bull analyst yet" in prompt


@pytest.mark.unit
def test_bull_still_receives_a_real_bear_argument():
    captured = {}
    create_bull_researcher(_capturing_llm(captured))(
        _state("Bear Analyst: valuation is stretched", 1)
    )
    prompt = captured["prompt"]
    assert "Last bear argument: Bear Analyst: valuation is stretched" in prompt
    assert "no responses from the bear analyst yet" not in prompt


@pytest.mark.unit
def test_bear_still_receives_a_real_bull_argument():
    captured = {}
    create_bear_researcher(_capturing_llm(captured))(
        _state("Bull Analyst: margins keep expanding", 1)
    )
    prompt = captured["prompt"]
    assert "Last bull argument: Bull Analyst: margins keep expanding" in prompt
    assert "no responses from the bull analyst yet" not in prompt
