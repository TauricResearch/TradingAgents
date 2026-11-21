"""Gom Pro Pack order flow: footprints, imbalances, levels, cumulative delta, profile."""

from __future__ import annotations

from unittest import mock

import numpy as np
import pandas as pd
import pytest

from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.dataflows.strategy_indicators import report
from tradingagents.dataflows.strategy_indicators.gom_order_flow import (
    Footprint,
    GomParams,
    analyse,
    build_footprints,
    imbalances,
    order_flow,
    order_flow_levels,
    value_area,
    volume_nodes,
)
from tradingagents.dataflows.vendors.yahoo.intraday import clean_intraday

from .test_strategy_indicators import _bars, hourly_from_daily

GOM = ("gom_order_flow", "gom_order_flow_levels", "gom_cumulative_delta", "gom_market_profile")


def _hourly(rows: list[tuple[str, float, float, float, float, float]]) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=["Datetime", "Open", "High", "Low", "Close", "Volume"])
    df["Datetime"] = pd.to_datetime(df["Datetime"])
    df["Session"] = df["Datetime"].dt.normalize()
    return df


def _fp(buys, sells, base: int = 100, level: float = 1.0) -> Footprint:
    buys, sells = np.asarray(buys, float), np.asarray(sells, float)
    n = len(buys)
    return Footprint(session=pd.Timestamp("2026-01-05"), level=level, base=base, buys=buys, sells=sells,
                     neutral=np.zeros(n), ticks=np.ones(n), open=base * level, high=(base + n - 1) * level,
                     low=base * level, close=base * level, vwap=base * level, bar_deltas=np.array([0.0]),
                     high_bar=0, low_bar=0)


# ---------------------------------------------------------------------------
# Footprint construction
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_bars_are_classified_by_the_up_down_tick_rule():
    bars = _hourly([
        ("2026-01-05 10:00", 10, 10, 10, 10, 100),   # no previous close: no direction
        ("2026-01-05 11:00", 10, 11, 10, 11, 200),   # up: buying
        ("2026-01-05 12:00", 11, 11, 11, 11, 300),   # unchanged: keeps buying
        ("2026-01-05 13:00", 11, 11, 10, 10, 400),   # down: selling
    ])
    (fp,) = build_footprints(bars, level=1.0)
    assert fp.neutral.sum() == 100
    assert fp.buys.sum() == 500
    assert fp.sells.sum() == 400
    assert list(fp.bar_deltas) == [0, 200, 300, -400]


@pytest.mark.unit
def test_a_bar_spreads_its_volume_over_the_levels_it_traded():
    bars = _hourly([("2026-01-05 10:00", 10, 10, 10, 10, 1),
                    ("2026-01-05 11:00", 10, 13, 10, 13, 400)])
    (fp,) = build_footprints(bars, level=1.0)
    assert fp.base == 10
    assert list(fp.buys) == [100, 100, 100, 100]


@pytest.mark.unit
def test_the_tick_rule_runs_across_sessions():
    bars = _hourly([("2026-01-05 15:00", 10, 10, 9, 9, 10), ("2026-01-05 16:00", 9, 9, 8, 8, 10),
                    ("2026-01-06 10:00", 8, 8, 8, 8, 50)])  # unchanged at the next open: still selling
    _, second = build_footprints(bars, level=1.0)
    assert second.sells.sum() == 50


# ---------------------------------------------------------------------------
# Imbalances, zones, reversals
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_diagonal_imbalance_compares_buys_with_sells_one_level_below():
    fp = _fp(buys=[5, 30, 9, 10], sells=[10, 10, 10, 40])
    is_buy, is_sell = imbalances(fp, GomParams(imbalance_min_winning_side_volume=0))
    # level 0: nothing traded below it, so any buying is one; level 1: 30 vs 10 -> 3x; level 2: 9 vs 10 no
    assert list(is_buy) == [True, True, False, False]
    # level 3: 40 sells vs no buys above -> imbalance; level 0: 10 sells vs 30 buys above -> no
    assert list(is_sell) == [False, False, False, True]


@pytest.mark.unit
def test_horizontal_and_second_criterion():
    fp = _fp(buys=[30, 30], sells=[10, 1])
    params = GomParams(imbalance_criterion1_direction="horizontal", imbalance_min_winning_side_volume=0,
                       imbalance_criterion2_direction="horizontal", imbalance_criterion2_comparison="difference",
                       imbalance_criterion2_value=25)
    is_buy, _ = imbalances(fp, params)
    assert list(is_buy) == [False, True]  # level 0 is 3x but only 20 more
    none = imbalances(fp, GomParams(imbalance_criterion1_direction="none"))
    assert not none[0].any() and not none[1].any()


@pytest.mark.unit
def test_the_winning_side_needs_the_minimum_volume():
    fp = _fp(buys=[0, 3, 0], sells=[1, 0, 0])
    assert imbalances(fp, GomParams(imbalance_min_winning_side_volume=0))[0][1]
    assert not imbalances(fp, GomParams(imbalance_min_winning_side_volume=5))[0][1]


@pytest.mark.unit
def test_stacked_buy_imbalances_make_a_support_zone():
    fp = _fp(buys=[0, 40, 40, 40, 1], sells=[10, 10, 10, 10, 10])
    s = analyse(fp, GomParams(imbalance_min_winning_side_volume=0))
    assert s["SupportZones"] == [(101.0, 103.0)]
    assert s["ResistanceZones"] == []
    assert s["NbBuyImbalances"] == 3


@pytest.mark.unit
def test_buying_that_declines_into_the_high_is_a_bearish_reversal():
    # buying falls 50 > 40 > 30 > 20 > 10 into the high: four declining levels
    fp = _fp(buys=[5, 50, 40, 30, 20, 10], sells=[45, 45, 45, 45, 45, 45])
    s = analyse(fp, GomParams(imbalance_min_winning_side_volume=0))
    assert s["BearishReversal"]
    assert not s["BullishReversal"]
    assert not analyse(fp, GomParams(min_num_of_declining_levels=5))["BearishReversal"]
    # a buy imbalance inside the declining zone vetoes it unless authorized
    strong = _fp(buys=[5, 200, 40, 30, 20, 10], sells=[45, 45, 45, 45, 45, 45])
    assert not analyse(strong, GomParams(imbalance_min_winning_side_volume=0))["BearishReversal"]
    assert analyse(strong, GomParams(imbalance_min_winning_side_volume=0,
                                     imbalance_in_declining_zone_authorized=True))["BearishReversal"]


@pytest.mark.unit
def test_unfinished_auction_is_both_sides_trading_the_extreme():
    s = analyse(_fp(buys=[5, 5, 5], sells=[0, 5, 5]))
    assert s["HighUA"] and not s["LowUA"]


@pytest.mark.unit
def test_invalid_options_are_rejected():
    with pytest.raises(ValueError, match="diagonal"):
        GomParams(imbalance_criterion1_direction="sideways")


# ---------------------------------------------------------------------------
# Levels, cumulative delta, profile
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_poc_traded_by_a_later_session_is_not_naked():
    table = pd.DataFrame({
        "Date": pd.bdate_range("2026-01-05", periods=3), "High": [12.0, 20.0, 14.0], "Low": [10.0, 15.0, 11.0],
        "Close": [11.0, 18.0, 12.0], "POCPrice": [11.0, 17.0, 12.0], "HighUA": False, "LowUA": False,
        "SupportZones": [[], [], []], "ResistanceZones": [[], [], []],
    })
    levels = order_flow_levels(table, level=1.0)
    naked = levels[levels["Kind"] == "naked POC"]
    assert list(naked["Low"]) == [17.0, 12.0]  # 11 was traded again on the third day


@pytest.mark.unit
def test_cumulative_delta_carries_from_session_to_session():
    hourly = clean_intraday(hourly_from_daily(_bars(n=60)), "2026-06-30", "X")
    table, _ = order_flow(hourly)
    assert np.allclose(table["CumDeltaOpen"].iloc[1:].to_numpy(), table["CumDeltaClose"].iloc[:-1].to_numpy())
    assert np.isclose(table["CumDeltaClose"].iloc[-1], table["Delta"].sum())
    assert (table["CumDeltaHigh"] >= table[["CumDeltaOpen", "CumDeltaClose"]].max(axis=1)).all()
    reset, _ = order_flow(hourly, GomParams(reinit_session=True))
    assert (reset["CumDeltaOpen"] == 0).all()
    assert np.allclose(reset["CumDeltaClose"], reset["Delta"])


@pytest.mark.unit
def test_value_area_grows_from_the_poc_toward_the_larger_neighbour():
    prof = np.array([1, 2, 10, 30, 20, 5, 1], float)
    poc, lo, hi = value_area(prof, 0.70)
    assert (poc, lo, hi) == (3, 3, 4)  # 50 of 69 = 72%
    hv, lv = volume_nodes(np.array([1, 5, 1, 1, 0, 1, 1, 9, 1], float), size=1, smooth=1)
    assert hv[0] == 7 and 1 in hv
    assert 4 in lv


# ---------------------------------------------------------------------------
# Report integration
# ---------------------------------------------------------------------------


@pytest.fixture
def hourly_market():
    daily = _bars()
    hourly = hourly_from_daily(daily.tail(300))
    with (mock.patch.object(report, "load_ohlcv", lambda s, d: daily.copy()),
          mock.patch.object(report, "load_intraday", lambda s, d: clean_intraday(hourly, d, s))):
        yield daily, hourly


@pytest.mark.unit
@pytest.mark.parametrize("name", GOM)
def test_gom_indicators_render(hourly_market, name):
    out = report.strategy_indicator_report("AAPL", name, "2026-06-30", 30)
    assert out.startswith("## Gom")
    assert "**Reading:**" in out and "Clean-room port" in out


@pytest.mark.unit
@pytest.mark.parametrize("name", GOM)
def test_no_hourly_bar_after_the_analysis_date_is_read(hourly_market, name):
    daily, hourly = hourly_market
    cut = "2026-03-16"
    full = report.strategy_indicator_report("AAPL", name, cut, 30)
    early = hourly[hourly["Datetime"] < pd.Timestamp(cut) + pd.Timedelta(days=1)]
    with mock.patch.object(report, "load_intraday", lambda s, d: clean_intraday(early, d, s)):
        assert report.strategy_indicator_report("AAPL", name, cut, 30) == full


@pytest.mark.unit
def test_a_date_before_the_hourly_history_is_no_data(hourly_market):
    with pytest.raises(NoMarketDataError, match="hourly history starts"):
        report.strategy_indicator_report("AAPL", "gom_order_flow", "2024-03-01", 30)


@pytest.mark.unit
def test_tz_aware_timestamps_keep_their_local_session():
    raw = pd.DataFrame({"Datetime": ["2026-01-05 09:30:00+03:00", "2026-01-05 23:30:00-05:00"],
                        "Open": [1, 1], "High": [1, 1], "Low": [1, 1], "Close": [1, 1], "Volume": [1, 1]})
    out = clean_intraday(raw, "2026-01-05", "X")
    assert (out["Session"] == pd.Timestamp("2026-01-05")).all()
