"""JFTS Forces: the port of the JFTS AutoTrader's indicator set."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradingagents.dataflows.strategy_indicators import INDICATOR_NAMES, report
from tradingagents.dataflows.strategy_indicators.jfts_forces import (
    JFTSParams,
    compute_jfts_forces,
    jfts_forces,
    volume_pressure,
)


def _frame(rows: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    dates = pd.bdate_range("2026-01-05", periods=len(rows))
    o, h, lo, c = zip(*rows, strict=True)
    return pd.DataFrame({"Date": dates, "Open": o, "High": h, "Low": lo, "Close": c, "Volume": 1.0})


def _bars(n: int = 500, seed: int = 4) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.017, n)))
    open_ = np.r_[close[0], close[:-1]] * np.exp(rng.normal(0, 0.006, n))
    high = np.maximum(open_, close) * np.exp(np.abs(rng.normal(0, 0.008, n)))
    low = np.minimum(open_, close) * np.exp(-np.abs(rng.normal(0, 0.008, n)))
    return pd.DataFrame({"Date": pd.bdate_range("2024-01-01", periods=n), "Open": open_, "High": high,
                         "Low": low, "Close": close, "Volume": 1.0})


def _impulse_pullback() -> pd.DataFrame:
    """Chop, a six-bar impulse up, a two-bar shallow pullback, then the trend resumes."""
    rows, p = [], 100.0
    for i in range(12):
        d = 1 if i % 4 < 2 else -1
        p += d
        rows.append((p - 0.3 * d, p + 0.6, p - 0.6, p))
    for _ in range(6):
        p += 2
        rows.append((p - 1.5, p + 0.5, p - 1.8, p))
    for _ in range(2):
        p -= 1
        rows.append((p + 0.8, p + 0.9, p - 0.4, p))
    for _ in range(4):
        p += 2
        rows.append((p - 1.5, p + 0.5, p - 1.8, p))
    return _frame(rows)


@pytest.mark.unit
def test_it_is_offered_with_the_other_strategy_indicators():
    assert "jfts_forces" in INDICATOR_NAMES
    assert report.STRATEGY_INDICATORS["jfts_forces"].compute is compute_jfts_forces


@pytest.mark.unit
def test_higher_highs_and_lows_are_a_bull_leg_and_lower_highs_a_bear_leg():
    up = _frame([(100 + i, 101 + i, 99 + i, 100.5 + i) for i in range(10)])
    down = _frame([(100 - i, 101 - i, 99 - i, 99.5 - i) for i in range(10)])
    assert set(jfts_forces(up)["Leg"].iloc[4:]) == {"bull"}
    assert set(jfts_forces(down)["Leg"].iloc[4:]) == {"bear"}


@pytest.mark.unit
def test_an_inside_bar_stays_in_the_leg():
    rows = [(100 + i, 101 + i, 99 + i, 100.5 + i) for i in range(8)]
    rows.append((107.2, 107.5, 106.5, 107.0))  # inside the bar before
    rows.append((107.4, 108.6, 107.1, 108.2))
    s = jfts_forces(_frame(rows))
    assert s["Leg"].iloc[-1] == "bull"  # decided on the bar after the inside bar


@pytest.mark.unit
def test_the_stops_are_the_ema_filter_rounded_to_the_tick():
    s = jfts_forces(_bars(), JFTSParams(tick_size=0.05))
    tail = s.iloc[5:]
    assert np.allclose(tail["StopLong"], (tail["EMAFilterLow"] / 0.05).round() * 0.05)
    assert np.allclose(tail["StopShort"], (tail["EMAFilterHigh"] / 0.05).round() * 0.05)


@pytest.mark.unit
def test_a_shallow_pullback_after_an_impulse_is_a_1b_long_entry():
    s = jfts_forces(_impulse_pullback())
    first = s[s["Signal"] != 0].iloc[0]
    assert first["Signal"] == 1 and first["Pattern"] == "1"
    assert first["Date"] == pd.Timestamp("2026-02-03")  # the first bar back up after the pullback
    assert first["StopLong"] < first["Close"]


@pytest.mark.unit
def test_switching_the_patterns_off_leaves_no_signal():
    s = jfts_forces(_bars(), JFTSParams(patterns=()))
    assert (s["Signal"] == 0).all() and (s["Pattern"] == "").all()


@pytest.mark.unit
def test_every_signal_has_its_pattern_its_filter_and_its_stop():
    s = jfts_forces(_bars())
    longs, shorts = s[s["Signal"] == 1], s[s["Signal"] == -1]
    assert len(longs) and len(shorts)
    assert (longs["PatternSide"] == 1).all() and (longs["ReadyBulls"] == 1).all()
    assert (longs["StopLongTicks"] < 0).all()
    assert (shorts["PatternSide"] == -1).all() and (shorts["ReadyBears"] == -1).all()
    assert (shorts["StopShortTicks"] < 0).all()


@pytest.mark.unit
def test_no_later_bar_changes_an_earlier_value():
    df = _bars()
    full = jfts_forces(df)
    part = jfts_forces(df.iloc[:300].copy())
    pd.testing.assert_frame_equal(part, full.iloc[:300].reset_index(drop=True))


@pytest.mark.unit
def test_volume_pressure_is_the_dominance_of_bullish_over_bearish_bodies():
    up = _frame([(100 + i, 101.5 + i, 99.5 + i, 101 + i) for i in range(30)])
    down = _frame([(101 - i, 101.5 - i, 99.5 - i, 100 - i) for i in range(30)])
    both = _frame([(100, 101.5, 99.5, 101) if i % 2 else (101, 101.5, 99.5, 100) for i in range(30)])
    assert np.allclose(volume_pressure(up, 20, 0.01)[5:], 100)
    assert np.allclose(volume_pressure(down, 20, 0.01)[5:], -100)
    assert np.allclose(volume_pressure(both, 20, 0.01)[20:], 0)
    assert (volume_pressure(up, 20, 0.01)[:5] == 0).all()


@pytest.mark.unit
def test_the_report_reads_the_last_bar():
    df = _bars()
    result = compute_jfts_forces(df, df["Date"].iloc[-1] - pd.Timedelta(days=90))
    assert result.headline
    titles = [t for t, _ in result.tables]
    assert "JFTS Forces" in titles
    facts = dict(result.facts)
    assert "EMA filter low / long stop" in facts and "Current leg" in facts
