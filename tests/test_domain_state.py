"""Acceptance tests for the research_state contract (domain/state.py)."""

from __future__ import annotations

import pytest

from tradingagents.domain import (
    AgentOpinion,
    Direction,
    Levels,
    ResearchState,
    RiskVerdict,
)

pytestmark = pytest.mark.unit


def test_direction_helpers():
    assert Direction.STRONG_BUY.is_long and Direction.STRONG_BUY.is_strong
    assert Direction.SELL.is_short and not Direction.SELL.is_strong
    assert not Direction.HOLD.is_actionable


def _actionable_state() -> ResearchState:
    return ResearchState(
        ticker="AAPL",
        market_view="m", sentiment_view="s",
        fundamental_view="f", technical_view="t",
        direction=Direction.BUY,
        conviction_level=Direction.BUY,
        levels=Levels(k_entry=0.5, k_stop=2, k_tp=3,
                      entry_price=180, stop_loss=170, take_profit=195),
        position_sizing_pct=0.05,
        agent_opinions=[
            AgentOpinion(agent="technical", suggested_direction=Direction.BUY,
                         suggested_conviction=Direction.BUY, rationale="uptrend"),
        ],
    )


def test_completeness_gate_actionable():
    state = _actionable_state()
    assert state.is_complete()
    # Missing prices -> not complete
    state.levels.entry_price = None
    assert not state.is_complete()


def test_completeness_gate_hold_needs_no_levels():
    state = ResearchState(
        ticker="AAPL",
        market_view="m", sentiment_view="s",
        fundamental_view="f", technical_view="t",
        direction=Direction.HOLD, conviction_level=Direction.HOLD,
    )
    assert state.is_complete()  # nothing to execute


def test_incomplete_when_view_missing():
    state = _actionable_state()
    state.technical_view = ""
    assert not state.is_complete()


def test_seal_produces_nested_document():
    state = _actionable_state()
    state.risk.verdict = RiskVerdict.APPROVED
    sealed = state.seal()
    assert set(sealed) == {"identity", "analysis", "proposal", "risk_gate", "meta"}
    assert sealed["proposal"]["direction"] == "buy"
    assert sealed["proposal"]["levels"]["entry_price"] == 180
    assert sealed["analysis"]["agent_opinions"][0]["agent"] == "technical"
    assert sealed["risk_gate"]["verdict"] == "approved"
    assert state.is_approved
