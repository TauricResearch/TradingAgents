"""Tests for the deterministic backtester."""

from __future__ import annotations

import pytest

from tradingagents.backtesting import backtest

pytestmark = pytest.mark.unit


def _trend_bars(n, start, step):
    bars = []
    for i in range(n):
        p = start + i * step
        bars.append({"open": p, "high": p + 2, "low": p - 2, "close": p})
    return bars


def test_backtest_uptrend_is_profitable():
    res = backtest(_trend_bars(120, 100.0, 1.0), k_entry=0.0, k_stop=2, k_tp=3, atr_period=14)
    assert res.num_trades > 0
    assert res.hit_rate > 0.5          # mostly take-profits in an uptrend
    assert res.total_return > 0


def test_backtest_downtrend_loses():
    res = backtest(_trend_bars(120, 300.0, -1.0), k_entry=0.0, k_stop=2, k_tp=3, atr_period=14)
    assert res.num_trades > 0
    assert res.total_return < 0         # stops dominate in a downtrend


def test_backtest_insufficient_data():
    res = backtest(_trend_bars(5, 100.0, 1.0))
    assert res.num_trades == 0
    assert res.total_return == 0.0
