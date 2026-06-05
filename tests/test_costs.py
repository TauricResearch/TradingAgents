"""Tests for commission models and the cost guardrail."""

from __future__ import annotations

import pytest

from tradingagents.broker import (
    PercentCommission,
    PerShareCommission,
    PerTradeCommission,
    ZeroCommission,
)
from tradingagents.domain import Levels
from tradingagents.execution import assess_costs, expected_reward, expected_risk

pytestmark = pytest.mark.unit


def test_commission_models():
    assert ZeroCommission().estimate("A", 10, 100) == 0.0
    assert PerTradeCommission(1.0).estimate("A", 10, 100) == 1.0
    assert PerTradeCommission(1.0).estimate("A", 0, 100) == 0.0
    # per-share with a per-order minimum
    assert PerShareCommission(0.01, min_fee=1.0).estimate("A", 10, 100) == 1.0  # 0.1 -> min 1
    assert PerShareCommission(0.01).estimate("A", 1000, 100) == pytest.approx(10.0)
    assert PercentCommission(0.001).estimate("A", 10, 100) == pytest.approx(1.0)


def _levels():
    return Levels(k_entry=0.5, k_stop=2, k_tp=3,
                  entry_price=100.0, stop_loss=90.0, take_profit=130.0)


def test_expected_reward_and_risk():
    lv = _levels()
    assert expected_reward(lv, 10) == pytest.approx(300.0)  # (130-100)*10
    assert expected_risk(lv, 10) == pytest.approx(100.0)    # (100-90)*10


def test_assess_costs_pass_and_fail():
    lv = _levels()
    ok = assess_costs(lv, 10, commission=5.0, token_cost=1.0)
    assert ok.ok and ok.net_expected_value == pytest.approx(294.0)

    bad = assess_costs(lv, 10, commission=500.0)
    assert not bad.ok and bad.net_expected_value < 0
