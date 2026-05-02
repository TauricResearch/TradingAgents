"""Smoke tests for pa.bars — verifies yfinance round-trip and resampling.

These are integration tests: they hit yfinance, so they need network
access. Skip them in CI by setting PA_SKIP_NETWORK=1.
"""

from __future__ import annotations

import os

import pandas as pd
import pytest

from pa.bars import fetch_bars, resample_weekly

pytestmark = pytest.mark.skipif(
    os.environ.get("PA_SKIP_NETWORK") == "1",
    reason="network-dependent (yfinance)",
)


def test_fetch_daily_nvda_returns_normalised_ohlcv():
    bars = fetch_bars("NVDA", "2024-05-01", "2024-05-31", timeframe="daily")
    assert list(bars.columns) == ["open", "high", "low", "close", "volume"]
    assert bars.index.tz is None
    assert bars.index.is_monotonic_increasing
    # 21 trading days in May 2024 (Memorial Day on the 27th is a holiday).
    assert 19 <= len(bars) <= 22, f"unexpected bar count: {len(bars)}"
    # No NaNs in OHLC; volume can be 0 in rare edge cases but never NaN.
    assert not bars[["open", "high", "low", "close"]].isna().any().any()
    # Sanity: high >= max(open, close), low <= min(open, close).
    assert (bars["high"] >= bars[["open", "close"]].max(axis=1) - 1e-6).all()
    assert (bars["low"]  <= bars[["open", "close"]].min(axis=1) + 1e-6).all()


def test_resample_weekly_aggregates_correctly():
    bars = fetch_bars("NVDA", "2024-05-01", "2024-05-31", timeframe="daily")
    weekly = resample_weekly(bars)
    # ~5 weeks span May 2024.
    assert 4 <= len(weekly) <= 6
    # Open/close monotone-week sanity: each weekly bar's high is at
    # least its weekly open and weekly close.
    assert (weekly["high"] >= weekly["open"] - 1e-6).all()
    assert (weekly["high"] >= weekly["close"] - 1e-6).all()
    assert (weekly["low"]  <= weekly["open"] + 1e-6).all()
    assert (weekly["low"]  <= weekly["close"] + 1e-6).all()
    # Volume should sum, not average — at least one weekly bar has volume
    # bigger than any single daily bar in that week.
    assert weekly["volume"].max() > bars["volume"].max()


def test_fetch_bars_rejects_bad_timeframe():
    with pytest.raises(ValueError, match="timeframe"):
        fetch_bars("NVDA", "2024-05-01", "2024-05-31", timeframe="hourly")  # type: ignore[arg-type]


def test_fetch_bars_raises_on_empty_response():
    # 2099 has no data — yfinance returns empty, we surface a clear error.
    with pytest.raises(ValueError, match="no bars"):
        fetch_bars("NVDA", "2099-01-01", "2099-01-31")
