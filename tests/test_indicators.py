"""Tests for the pure indicator math (indicators/core.py)."""

from __future__ import annotations

import pytest

from tradingagents.indicators import (
    atr,
    compute_indicator,
    ema,
    high_low_52w,
    max_drawdown,
    rsi,
    sma,
)

pytestmark = pytest.mark.unit


def _flat_bars(n: int, close: float = 100.0, half_range: float = 1.0):
    # Each bar: high=close+1, low=close-1 -> TR = 2 for every bar after the first.
    return [{"high": close + half_range, "low": close - half_range, "close": close}
            for _ in range(n)]


def test_atr_constant_true_range():
    bars = _flat_bars(20)  # every TR = 2.0
    assert atr(bars, period=14) == pytest.approx(2.0)


def test_atr_insufficient_data():
    assert atr(_flat_bars(5), period=14) is None


def test_rsi_extremes():
    up = [float(x) for x in range(1, 30)]      # strictly increasing
    down = [float(x) for x in range(30, 1, -1)]  # strictly decreasing
    assert rsi(up, 14) == pytest.approx(100.0)
    assert rsi(down, 14) == pytest.approx(0.0)


def test_sma_and_ema_constant():
    vals = [5.0] * 10
    assert sma(vals, 5) == pytest.approx(5.0)
    assert ema(vals, 5) == pytest.approx(5.0)
    assert sma([1.0, 2.0], 5) is None


def test_max_drawdown():
    assert max_drawdown([100, 120, 90, 150]) == pytest.approx(0.25)
    assert max_drawdown([]) == 0.0


def test_range_position():
    bars = [{"high": 110, "low": 90, "close": 100} for _ in range(3)]
    info = high_low_52w(bars)
    assert info["high"] == 110 and info["low"] == 90
    assert info["range_position"] == pytest.approx(0.5)


def test_compute_indicator_dispatch_and_unknown():
    bars = _flat_bars(20)
    assert compute_indicator("atr", bars, period=14) == pytest.approx(2.0)
    with pytest.raises(ValueError):
        compute_indicator("bogus", bars)
