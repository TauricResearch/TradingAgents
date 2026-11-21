"""Strategy indicators: the calculations, the report, and the analyst's tool."""

from __future__ import annotations

from unittest import mock

import numpy as np
import pandas as pd
import pytest

from tradingagents.agents import tools
from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.dataflows.strategy_indicators import INDICATOR_NAMES, calc, report
from tradingagents.dataflows.vendors.yahoo.intraday import clean_intraday

AS_OF = "2026-06-30"


def _bars(n: int = 700, seed: int = 1, volume: bool = True, start: str = "2023-09-01") -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start, periods=n)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.017, n)))
    open_ = np.r_[close[0], close[:-1]] * np.exp(rng.normal(0, 0.006, n))
    high = np.maximum(open_, close) * np.exp(np.abs(rng.normal(0, 0.008, n)))
    low = np.minimum(open_, close) * np.exp(-np.abs(rng.normal(0, 0.008, n)))
    vol = rng.integers(100_000, 1_000_000, n).astype(float) if volume else np.zeros(n)
    return pd.DataFrame({"Date": dates, "Open": open_, "High": high, "Low": low, "Close": close, "Volume": vol})


def _frame(rows: list[tuple[float, float, float, float]], volume: float = 1000.0) -> pd.DataFrame:
    dates = pd.bdate_range("2026-01-05", periods=len(rows))
    o, h, lo, c = zip(*rows, strict=True)
    return pd.DataFrame({"Date": dates, "Open": o, "High": h, "Low": lo, "Close": c, "Volume": volume})


def hourly_from_daily(daily: pd.DataFrame, seed: int = 0, bars_per_day: int = 7) -> pd.DataFrame:
    """Hourly bars inside each daily bar: a noisy path from the open to the close."""
    rng = np.random.default_rng(seed)
    rows = []
    inner = np.r_[0, np.ones(bars_per_day - 1), 0]
    for d in daily.itertuples(index=False):
        path = np.linspace(d.Open, d.Close, bars_per_day + 1) + rng.normal(0, 0.2 * (d.High - d.Low), bars_per_day + 1) * inner
        path = np.clip(path, d.Low, d.High)
        for k in range(bars_per_day):
            o, c = path[k], path[k + 1]
            rows.append((d.Date + pd.Timedelta(hours=10 + k), o, max(o, c), min(o, c), c, d.Volume / bars_per_day))
    return pd.DataFrame(rows, columns=["Datetime", "Open", "High", "Low", "Close", "Volume"])


@pytest.fixture
def market():
    data = {"AAPL": _bars(), "SPY": _bars(seed=2), "FLAT": _bars(seed=3, volume=False)}
    # Yahoo serves about two years of hourly bars; the order-flow indicators read them.
    hourly = {k: hourly_from_daily(v.tail(500)) for k, v in data.items()}
    with (mock.patch.object(report, "load_ohlcv", lambda symbol, as_of_date: data[symbol].copy()),
          mock.patch.object(report, "load_intraday",
                            lambda symbol, as_of_date: clean_intraday(hourly[symbol], as_of_date, symbol))):
        yield data


# ---------------------------------------------------------------------------
# Every indicator renders
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("name", INDICATOR_NAMES)
@pytest.mark.parametrize("symbol", ["AAPL", "FLAT"], ids=["with-volume", "no-volume"])
def test_every_indicator_renders_a_report(market, name, symbol):
    out = report.strategy_indicator_report(symbol, name, AS_OF, 60)
    assert out.startswith("## ")
    assert symbol in out
    assert "could not be computed" not in out
    assert "| nan" not in out.lower() and " nan |" not in out.lower()  # NaN renders as N/A


@pytest.mark.unit
def test_the_summary_has_one_line_per_indicator(market):
    out = report.strategy_indicator_report("AAPL", "strategy_summary", AS_OF, 60)
    for name in report.STRATEGY_INDICATORS:
        assert f"| {name} |" in out


@pytest.mark.unit
def test_no_bar_after_the_analysis_date_is_read(market):
    """The report as of a date is the same whether or not later bars exist."""
    cut = "2025-12-15"
    full = {name: report.strategy_indicator_report("AAPL", name, cut, 60) for name in INDICATOR_NAMES}
    truncated = {k: v[v["Date"] <= cut] for k, v in market.items()}
    with mock.patch.object(report, "load_ohlcv", lambda symbol, as_of_date: truncated[symbol].copy()):
        for name in INDICATOR_NAMES:
            assert report.strategy_indicator_report("AAPL", name, cut, 60) == full[name], name


@pytest.mark.unit
def test_an_unknown_indicator_names_the_valid_ones(market):
    with pytest.raises(ValueError, match="volume_profile"):
        report.strategy_indicator_report("AAPL", "magic_tape", AS_OF, 60)


@pytest.mark.unit
def test_too_short_a_history_is_no_data():
    short = _bars(n=12)
    with (mock.patch.object(report, "load_ohlcv", lambda s, d: short.copy()),
          pytest.raises(NoMarketDataError, match="30 are needed")):
        report.strategy_indicator_report("AAPL", "pivots", AS_OF, 60)


@pytest.mark.unit
@pytest.mark.parametrize("symbol, benchmark", [
    ("AAPL", "SPY"), ("THYAO.IS", "XU100.IS"), ("ETH-USD", "BTC-USD"),
])
def test_the_benchmark_follows_the_market(symbol, benchmark):
    assert report.benchmark_for(symbol) == benchmark


@pytest.mark.unit
def test_the_benchmark_itself_is_not_compared_with_itself(market):
    out = report.strategy_indicator_report("SPY", "relative_strength", AS_OF, 60)
    assert "its own benchmark" in out


# ---------------------------------------------------------------------------
# Calculations against hand-worked values
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_zigzag_finds_the_swings_and_leaves_the_last_one_forming():
    closes = [100, 104, 110, 106, 98, 95, 101, 108, 115, 112]
    df = _frame([(c, c, c, c) for c in closes])
    pivots = calc.zigzag(df, threshold=0.05)
    assert [(p.kind, p.price, p.confirmed) for p in pivots] == [
        ("L", 100.0, True), ("H", 110.0, True), ("L", 95.0, True), ("H", 115.0, False),
    ]
    assert calc.label_structure(pivots) == ["-", "-", "LL", "HH"]


@pytest.mark.unit
def test_value_area_grows_from_the_point_of_control():
    edges = np.arange(0.0, 11.0)               # ten 1-wide bins
    profile = np.array([1, 1, 2, 5, 20, 8, 3, 1, 1, 1], dtype=float)
    poc, val, vah = calc.value_area(edges, profile)
    assert poc == 4.5
    # 20, then the fuller neighbour: +8 (28), +5 (33) of 43 = 77% >= 70%
    assert (val, vah) == (3.0, 6.0)


@pytest.mark.unit
def test_classic_pivots():
    levels = calc._pivot_levels(110.0, 90.0, 100.0)
    assert levels["P"] == 100.0
    assert (levels["R1"], levels["S1"]) == (110.0, 90.0)
    assert (levels["R2"], levels["S2"]) == (120.0, 80.0)
    assert (levels["R3"], levels["S3"]) == (130.0, 70.0)
    assert levels["Camarilla H3"] == pytest.approx(105.5)


@pytest.mark.unit
def test_weekly_pivots_come_from_the_previous_completed_week():
    df = _bars(n=60)
    out = calc.compute_pivots(df, df["Date"].iloc[-20])
    last_week = df["Date"].iloc[-1].to_period("W")
    prior = df[df["Date"].dt.to_period("W") == last_week - 1]
    weekly = dict(out.tables[0][1].set_index("Level")["Weekly"])
    assert weekly["Period high"] == prior["High"].max()
    assert weekly["Period low"] == prior["Low"].min()


@pytest.mark.unit
def test_a_gap_up_stays_open_until_price_trades_back_through_it():
    rows = [(100, 101, 99, 100)] * 20
    rows += [(105, 106, 104, 105.5)] * 5          # gap up: zone 101 -> 104, never revisited
    rows += [(103, 104.5, 102, 103)]              # partly fills it, down to 102
    df = _frame(rows)
    res = calc.compute_gaps(df, df["Date"].iloc[0])
    gap = res.tables[0][1].iloc[0]
    assert (gap["Direction"], gap["Zone low"], gap["Zone high"]) == ("up", 101, 104)
    assert gap["Status"] == "partly filled" and gap["Unfilled high"] == 102

    df = _frame(rows + [(101, 102.5, 100.5, 101)])  # trades back to 100.5: filled
    res = calc.compute_gaps(df, df["Date"].iloc[0])
    assert "0 unfilled" in res.headline


@pytest.mark.unit
def test_a_bullish_engulfing_in_a_downtrend_is_found():
    rows = [(120 - i, 120.5 - i, 118.5 - i, 119 - i) for i in range(20)]    # steady decline
    last_close = rows[-1][3]
    rows.append((last_close + 0.2, last_close + 0.4, last_close - 1.6, last_close - 1.4))  # bearish
    rows.append((last_close - 1.6, last_close + 0.9, last_close - 1.8, last_close + 0.6))  # engulfs it
    found = calc.detect_candles(_frame(rows))
    assert (len(rows) - 1, "Bullish engulfing", "bullish") in found


@pytest.mark.unit
def test_supertrend_is_up_in_a_steady_rise():
    rows = [(100 + i, 101 + i, 99 + i, 100.5 + i) for i in range(60)]
    df = _frame(rows)
    res = calc.compute_supertrend(df, df["Date"].iloc[-10])
    assert dict(res.facts)["Direction"] == "up"


@pytest.mark.unit
def test_ichimoku_lines_are_high_low_midpoints_and_the_cloud_is_projected():
    df = _bars(n=120)
    ich = calc.ichimoku(df)
    last = df.tail(9)
    assert ich["Tenkan"].iloc[-1] == pytest.approx((last["High"].max() + last["Low"].min()) / 2)
    k = df.tail(26)
    assert ich["Kijun"].iloc[-1] == pytest.approx((k["High"].max() + k["Low"].min()) / 2)
    assert ich["SpanA"].iloc[-1] == pytest.approx(ich["LeadA"].iloc[-26])  # projected 25 bars ahead
    assert ich["SpanB"].iloc[-1] == pytest.approx(ich["LeadB"].iloc[-26])
    assert ich["Cloud top"].iloc[-1] >= ich["Cloud bottom"].iloc[-1]


@pytest.mark.unit
def test_weekly_bars_are_built_from_the_daily_ones():
    df = _bars(n=60)
    weekly = calc.resample_bars(df, "W")
    week = df[df["Date"].dt.to_period("W") == weekly.index[3]]
    row = weekly.iloc[3]
    assert (row["Open"], row["High"], row["Low"], row["Close"]) == (
        week["Open"].iloc[0], week["High"].max(), week["Low"].min(), week["Close"].iloc[-1])


@pytest.mark.unit
def test_mtf_ichimoku_goes_long_in_a_steady_rise_and_the_stop_only_ratchets_up():
    rows = [(100 + 0.3 * i, 101 + 0.3 * i, 99 + 0.3 * i, 100.6 + 0.3 * i) for i in range(500)]
    df = _frame(rows)
    res = calc.compute_mtf_ichimoku(df, df["Date"].iloc[0])
    facts = dict(res.facts)
    assert facts["Daily bias"] == "bullish" and facts["Weekly bias"] == "bullish"
    assert facts["Daily signal"].startswith("long since")
    series = dict(res.tables)["Daily Ichimoku"]
    held = series[series["Signal"] == "long"]["Trailing stop"]
    assert (held.diff().dropna() >= 0).all()
    assert held.iloc[-1] < df["Close"].iloc[-1]


@pytest.mark.unit
def test_mtf_ichimoku_reverses_to_short_when_the_trend_turns():
    up = [(100 + 0.3 * i, 101 + 0.3 * i, 99 + 0.3 * i, 100.6 + 0.3 * i) for i in range(300)]
    top = up[-1][3]
    down = [(top - 0.4 * i, top + 1 - 0.4 * i, top - 1 - 0.4 * i, top - 0.6 - 0.4 * i) for i in range(1, 200)]
    df = _frame(up + down)
    res = calc.compute_mtf_ichimoku(df, df["Date"].iloc[0])
    events = list(dict(res.tables)["Daily signals in window"]["Event"])
    assert events[0] == "long entry"
    assert "long exit (stop)" in events
    assert dict(res.facts)["Daily bias"] == "bearish"


@pytest.mark.unit
def test_relative_volume_compares_with_the_prior_bars_only():
    rows = [(100, 101, 99, 100)] * 25
    df = _frame(rows)
    df.loc[df.index[-1], "Volume"] = 3000.0
    res = calc.compute_relative_volume(df, df["Date"].iloc[-5])
    assert dict(res.facts)["Latest RVOL (vs prior 20-bar average)"] == "3.00×"


@pytest.mark.unit
def test_vwap_without_volume_falls_back_to_equal_weights():
    df = _bars(n=80, volume=False)
    res = calc.compute_vwap_bands(df, df["Date"].iloc[-10])
    tp = ((df["High"] + df["Low"] + df["Close"]) / 3).tail(20).mean()
    assert dict(res.facts)["Rolling 20-bar VWAP"] == calc.num(tp)
    assert any("no volume" in n for n in res.notes)


# ---------------------------------------------------------------------------
# The tool
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_fibonacci_confluence_pairs_consecutive_swings_only():
    """With fewer than seven swings every leg is still two different pivots."""
    full = _bars(n=400)
    df = next(full.head(n) for n in range(40, 400, 10) if 3 <= len(calc.zigzag(full.head(n))) < 7)
    res = calc.compute_fibonacci(df, df["Date"].iloc[-30])
    for title, table in res.tables:
        if title.startswith("Confluence"):
            for built in table["Built from"]:
                for part in built.split("; "):
                    start, end = part.split(" ")[-1].split("→")
                    assert start != end


@pytest.mark.unit
def test_the_tool_is_offered_to_the_market_analyst():
    from tradingagents.agents.analysts import market_analyst

    assert tools.get_strategy_indicator in market_analyst.TOOLS


@pytest.mark.unit
def test_the_tool_serves_the_run_instrument_and_date():
    with mock.patch.object(tools, "strategy_indicator_report", return_value="ok") as rep:
        out = tools.get_strategy_indicator.func(
            "NVDA", "pivots, gaps", "2026-09-14", 30, trade_date="2026-08-14")
    assert out == "ok\n\nok"
    assert rep.call_args_list == [mock.call("NVDA", "pivots", "2026-08-14", 30),
                                  mock.call("NVDA", "gaps", "2026-08-14", 30)]


@pytest.mark.unit
def test_the_tool_reports_failures_instead_of_raising():
    def boom(symbol, name, *a):
        if name == "pivots":
            raise NoMarketDataError(symbol, symbol, "no price rows")
        raise RuntimeError("bad")

    with mock.patch.object(tools, "strategy_indicator_report", side_effect=boom):
        out = tools.get_strategy_indicator.func("NVDA", "pivots,gaps", "2026-08-14", trade_date="2026-08-14")
    assert "NO_DATA_AVAILABLE" in out and "DATA_UNAVAILABLE: gaps could not be computed" in out


@pytest.mark.unit
def test_the_tool_passes_an_unknown_name_back_to_the_model(market):
    out = tools.get_strategy_indicator.func("AAPL", "bookmap", AS_OF, trade_date=AS_OF)
    assert "not supported" in out and "supply_demand" in out
