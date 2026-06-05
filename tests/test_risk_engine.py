"""Acceptance tests for the deterministic risk engine (domain/risk.py)."""

from __future__ import annotations

import pytest

from tradingagents.domain import (
    Direction,
    atr_levels,
    check_guardrails,
    conviction_multiplier,
    passes_risk_reward,
    position_size,
    risk_reward,
)

pytestmark = pytest.mark.unit


# --- ATR levels -----------------------------------------------------------
def test_atr_levels_long():
    lv = atr_levels(100.0, 2.0, Direction.BUY, k_entry=0.5, k_stop=2, k_tp=3)
    assert lv.entry_price == pytest.approx(99.0)   # 100 - 0.5*2
    assert lv.stop_loss == pytest.approx(95.0)     # 99 - 2*2
    assert lv.take_profit == pytest.approx(105.0)  # 99 + 3*2


def test_atr_levels_short_is_mirrored():
    lv = atr_levels(100.0, 2.0, Direction.SELL, k_entry=0.5, k_stop=2, k_tp=3)
    assert lv.entry_price == pytest.approx(101.0)
    assert lv.stop_loss == pytest.approx(105.0)
    assert lv.take_profit == pytest.approx(95.0)


def test_atr_levels_hold_raises():
    with pytest.raises(ValueError):
        atr_levels(100.0, 2.0, Direction.HOLD, k_entry=0.5, k_stop=2, k_tp=3)


# --- R:R ------------------------------------------------------------------
def test_risk_reward_and_guardrail():
    assert risk_reward(3, 2) == pytest.approx(1.5)
    assert passes_risk_reward(3, 2, min_rr=1.5)
    assert not passes_risk_reward(2, 2, min_rr=1.5)


# --- Conviction multiplier ------------------------------------------------
def test_conviction_multiplier():
    assert conviction_multiplier(Direction.HOLD) == 0.0
    assert conviction_multiplier(Direction.BUY) == 1.0
    assert conviction_multiplier(Direction.STRONG_BUY) > 1.0


# --- Position sizing ------------------------------------------------------
def test_position_size_basic():
    # 100k portfolio, 1% base risk, BUY (mult 1.0) -> 1000 euro at risk
    # stop_distance 5 -> 200 shares; price 100 -> 20k position (20% > 10% cap)
    r = position_size(100_000, 100.0, 5.0, Direction.BUY,
                      base_risk_pct=0.01, max_position_pct=0.10)
    # capped by max_position to 10k -> 100 shares
    assert r.capped_by == "max_position"
    assert r.position_value == pytest.approx(10_000)
    assert r.quantity == pytest.approx(100)


def test_position_size_uncapped():
    # wide stop keeps the position small enough to avoid the cap
    r = position_size(100_000, 100.0, 20.0, Direction.BUY,
                      base_risk_pct=0.01, max_position_pct=0.10)
    assert r.capped_by is None
    assert r.euro_at_risk == pytest.approx(1000)
    assert r.quantity == pytest.approx(50)  # 1000 / 20


def test_position_size_hold_is_zero():
    r = position_size(100_000, 100.0, 5.0, Direction.HOLD)
    assert r.quantity == 0.0
    assert r.capped_by == "no_budget"


def test_position_size_portfolio_heat_cap():
    # already used 5.5% of a 6% heat budget -> only 0.5% remains
    r = position_size(100_000, 100.0, 50.0, Direction.STRONG_BUY,
                      base_risk_pct=0.01, heat_used_pct=0.055, heat_max_pct=0.06)
    assert r.capped_by == "portfolio_heat"
    assert r.risk_pct == pytest.approx(0.005)
    assert r.euro_at_risk == pytest.approx(500)


# --- Guardrails -----------------------------------------------------------
def test_check_guardrails_pass_and_fail():
    lv = atr_levels(100.0, 2.0, Direction.BUY, k_entry=0.5, k_stop=2, k_tp=3)
    good = position_size(100_000, 100.0, 20.0, Direction.BUY, max_position_pct=0.10)
    checks = check_guardrails(levels=lv, sizing=good)
    assert checks["all_ok"]
    assert checks["risk_reward"]["ok"]

    bad_lv = atr_levels(100.0, 2.0, Direction.BUY, k_entry=0.5, k_stop=3, k_tp=3)  # R:R = 1.0
    checks2 = check_guardrails(levels=bad_lv, sizing=good, charter={"min_risk_reward": 1.5})
    assert not checks2["risk_reward"]["ok"]
    assert not checks2["all_ok"]
