"""Tests for state initialization (tradingagents/graph/propagation.py).

Verifies that create_initial_state produces complete InvestDebateState and
RiskDebateState dicts with all required fields (the incomplete-state bug fix).
"""

from tradingagents.graph.propagation import Propagator

INVEST_DEBATE_FIELDS = [
    "bull_history",
    "bear_history",
    "history",
    "current_response",
    "judge_decision",
    "count",
]

RISK_DEBATE_FIELDS = [
    "aggressive_history",
    "conservative_history",
    "neutral_history",
    "history",
    "latest_speaker",
    "current_aggressive_response",
    "current_conservative_response",
    "current_neutral_response",
    "judge_decision",
    "count",
]


def _initial_state():
    return Propagator().create_initial_state("AAPL", "2025-01-01")


def test_initial_invest_debate_state_has_all_fields():
    state = _initial_state()
    invest = state["investment_debate_state"]
    for field in INVEST_DEBATE_FIELDS:
        assert field in invest, f"InvestDebateState missing field: {field}"


def test_initial_risk_debate_state_has_all_fields():
    state = _initial_state()
    risk = state["risk_debate_state"]
    for field in RISK_DEBATE_FIELDS:
        assert field in risk, f"RiskDebateState missing field: {field}"


def test_initial_state_fields_are_empty_defaults():
    state = _initial_state()

    invest = state["investment_debate_state"]
    for field in INVEST_DEBATE_FIELDS:
        if field == "count":
            assert invest[field] == 0, f"InvestDebateState.{field} should be 0"
        else:
            assert invest[field] == "", f"InvestDebateState.{field} should be empty string"

    risk = state["risk_debate_state"]
    for field in RISK_DEBATE_FIELDS:
        if field == "count":
            assert risk[field] == 0, f"RiskDebateState.{field} should be 0"
        else:
            assert risk[field] == "", f"RiskDebateState.{field} should be empty string"
