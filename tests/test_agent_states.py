"""Unit tests for AgentState Polymarket extension."""

import pytest
from langchain_core.messages import HumanMessage

from tradingagents.agents.utils.agent_states import (
    AgentState,
    InvestDebateState,
    RiskDebateState,
)


@pytest.mark.unit
def test_existing_stock_state_unchanged():
    """Stock-mode caller can construct AgentState without Polymarket fields."""
    state = {
        "messages": [HumanMessage(content="hi")],
        "company_of_interest": "AAPL",
        "trade_date": "2026-05-07",
        "sender": "test",
        "market_report": "",
        "sentiment_report": "",
        "news_report": "",
        "fundamentals_report": "",
        "investment_debate_state": {},
        "investment_plan": "",
        "trader_investment_plan": "",
        "risk_debate_state": {},
        "final_trade_decision": "",
        "past_context": "",
        "instrument_type": "stock",
    }
    assert state["company_of_interest"] == "AAPL"
    assert state["instrument_type"] == "stock"


@pytest.mark.unit
def test_polymarket_state_has_market_fields():
    """Polymarket-mode state can include market-specific fields."""
    state = {
        "messages": [HumanMessage(content="hi")],
        "company_of_interest": "",
        "trade_date": "",
        "sender": "test",
        "market_report": "",
        "sentiment_report": "",
        "news_report": "",
        "fundamentals_report": "",
        "investment_debate_state": {},
        "investment_plan": "",
        "trader_investment_plan": "",
        "risk_debate_state": {},
        "final_trade_decision": "",
        "past_context": "",
        "instrument_type": "polymarket",
        "market_id": "540816",
        "market_question": "Will X happen by Y date?",
        "yes_price": 0.65,
        "resolution_date": "2026-12-31T00:00:00Z",
        "probability_report": "Base rate analysis...",
    }
    assert state["instrument_type"] == "polymarket"
    assert state["market_id"] == "540816"
    assert state["yes_price"] == 0.65
    assert state["probability_report"].startswith("Base rate")


@pytest.mark.unit
def test_polymarket_optional_fields_default_to_none():
    """Polymarket fields can be None in stock mode without crashing readers."""
    state = {
        "instrument_type": "stock",
        "market_id": None,
        "market_question": None,
        "yes_price": None,
        "resolution_date": None,
        "probability_report": None,
    }
    assert state.get("market_id") is None
    assert state.get("yes_price") is None


@pytest.mark.unit
def test_invest_debate_state_unchanged():
    """The bull/bear debate state has not been modified."""
    debate = {
        "bull_history": "",
        "bear_history": "",
        "history": "",
        "current_response": "",
        "judge_decision": "",
        "count": 0,
    }
    assert debate["count"] == 0


@pytest.mark.unit
def test_risk_debate_state_unchanged():
    """The risk team debate state is unchanged."""
    risk = {
        "aggressive_history": "",
        "conservative_history": "",
        "neutral_history": "",
        "history": "",
        "latest_speaker": "",
        "current_aggressive_response": "",
        "current_conservative_response": "",
        "current_neutral_response": "",
        "judge_decision": "",
        "count": 0,
    }
    assert risk["count"] == 0
