"""UniRenko bars and prior-day levels: the EPyF Basic Pack equivalent."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradingagents.dataflows.strategy_indicators import INDICATOR_NAMES, report
from tradingagents.dataflows.strategy_indicators.calc import num
from tradingagents.dataflows.strategy_indicators.unirenko import (
    UniRenkoParams,
    compute_unirenko,
    offsets,
    unirenko,
)

FIXED = UniRenkoParams(trend=1.0, reversal=3.0, tick_size=0.01)


def _frame(rows: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    dates = pd.bdate_range("2026-01-05", periods=len(rows))
    o, h, lo, c = zip(*rows, strict=True)
    return pd.DataFrame({"Date": dates, "Open": o, "High": h, "Low": lo, "Close": c, "Volume": 1.0})


def _bars(n: int = 400, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.017, n)))
    open_ = np.r_[close[0], close[:-1]] * np.exp(rng.normal(0, 0.006, n))
    high = np.maximum(open_, close) * np.exp(np.abs(rng.normal(0, 0.008, n)))
    low = np.minimum(open_, close) * np.exp(-np.abs(rng.normal(0, 0.008, n)))
    return pd.DataFrame({"Date": pd.bdate_range("2024-01-01", periods=n), "Open": open_, "High": high,
                         "Low": low, "Close": close, "Volume": 1.0})


@pytest.mark.unit
def test_it_is_offered_with_the_other_strategy_indicators():
    assert "unirenko" in INDICATOR_NAMES
    assert report.STRATEGY_INDICATORS["unirenko"].compute is compute_unirenko


@pytest.mark.unit
def test_a_steady_rise_completes_one_up_bar_per_trend_offset():
    # Open 100, each day closes 1.0 higher with no wick below the open.
    rows = [(100 + i, 101 + i, 100 + i, 101 + i) for i in range(5)]
    bricks, daily, _ = unirenko(_frame(rows), FIXED)
    assert bricks["Direction"].tolist() == [1] * 5
    assert bricks["Close"].tolist() == [101.0, 102.0, 103.0, 104.0, 105.0]
    assert daily["UpEnd"].iloc[-1] == pytest.approx(106.0)
    assert daily["DownEnd"].iloc[-1] == pytest.approx(102.0)  # one reversal offset below the last close


@pytest.mark.unit
def test_a_pullback_smaller_than_the_reversal_offset_does_not_turn_the_trend():
    rows = [(100, 103, 100, 103), (103, 103, 100.5, 100.5)]  # up three bars, then down 2.5 < 3.0
    bricks, daily, _ = unirenko(_frame(rows), FIXED)
    assert bricks["Direction"].tolist() == [1, 1, 1]
    assert daily["Direction"].iloc[-1] == 1
    assert daily["DownEnd"].iloc[-1] == pytest.approx(100.0)


@pytest.mark.unit
def test_a_move_of_one_reversal_offset_turns_the_trend_and_then_continues_by_trend_offsets():
    rows = [(100, 103, 100, 103), (103, 103, 98.9, 98.9)]  # up to 103, then down 4.1
    bricks, daily, _ = unirenko(_frame(rows), FIXED)
    assert bricks["Direction"].tolist() == [1, 1, 1, -1, -1]
    assert bricks["Close"].tolist()[-2:] == [100.0, 99.0]
    assert bricks["Reversal"].tolist() == [False, False, False, True, False]
    assert daily["UpEnd"].iloc[-1] == pytest.approx(102.0)  # turning back up needs a reversal offset
    assert daily["DownEnd"].iloc[-1] == pytest.approx(98.0)


@pytest.mark.unit
def test_the_day_path_visits_the_low_before_the_high_on_an_up_day():
    # Up day with a deep wick: open 100, low 96.9, high 101, close 101. Falling first completes
    # three down bars (99, 98, 97); the climb then turns up at 100 (one reversal) and continues to 101.
    bricks, _, _ = unirenko(_frame([(100, 101, 96.9, 101)]), FIXED)
    assert bricks["Close"].tolist() == [99.0, 98.0, 97.0, 100.0, 101.0]
    assert bricks["Direction"].tolist() == [-1, -1, -1, 1, 1]


@pytest.mark.unit
def test_a_bar_records_the_extremes_traded_while_it_formed():
    rows = [(100, 100.6, 99.5, 100.4), (100.4, 101.2, 100.2, 101.2)]
    bricks, _, _ = unirenko(_frame(rows), FIXED)
    first = bricks.iloc[0]
    assert (first["Open"], first["Close"], first["Direction"]) == (100.0, 101.0, 1)
    assert first["Low"] == pytest.approx(99.5)
    assert first["High"] == pytest.approx(101.0)


@pytest.mark.unit
def test_the_open_offset_moves_the_drawn_open_only():
    rows = [(100 + i, 101 + i, 100 + i, 101 + i) for i in range(3)]
    plain, _, _ = unirenko(_frame(rows), FIXED)
    shifted, _, _ = unirenko(_frame(rows), UniRenkoParams(trend=1.0, reversal=3.0, open_offset=0.5, tick_size=0.01))
    assert plain["Close"].tolist() == shifted["Close"].tolist()
    assert shifted["Open"].tolist() == [100.0, 100.5, 101.5]


@pytest.mark.unit
def test_default_offsets_follow_the_atr_on_the_tick_grid():
    df = _bars()
    off = offsets(df)
    assert off.reversal == pytest.approx(3 * off.trend, abs=0.02)
    assert off.trend == pytest.approx(0.5 * off.atr, abs=0.01)
    assert round(off.trend / off.tick, 6) == round(off.trend / off.tick)


@pytest.mark.unit
def test_flat_prices_complete_no_bar_and_still_report():
    df = _frame([(50.0, 50.0, 50.0, 50.0)] * 40)
    result = compute_unirenko(df, df["Date"].iloc[0])
    assert result.headline.startswith("No UniRenko bar has completed yet")


@pytest.mark.unit
def test_the_report_gives_the_open_bar_ends_and_the_prior_day_levels():
    df = _bars()
    result = compute_unirenko(df, df["Date"].iloc[-60])
    facts = dict(result.facts)
    prior = df.iloc[-2]
    assert facts["Prior-day high"].startswith(num(float(prior["High"])))
    assert "Up end (completes up)" in facts and "Down end (completes down)" in facts
    levels = dict(result.tables)["Level map (open bar ends and prior-day levels)"]
    assert levels["Price"].is_monotonic_decreasing
    assert set(levels["Level"]) == {"Up end", "Down end", "Prior-day high", "Prior-day low", "Prior-day open"}
    assert "UniRenko" in result.headline
