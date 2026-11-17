"""A date without a daily bar is reported as that, not as a closed market.

Crypto trades every day, and Yahoo withholds the day just ended from its daily
series for some hours after 00:00 UTC. The indicator table used to call every
missing date "Not a trading day (weekend or holiday)", and the analyst repeated
it for a coin.
"""

from __future__ import annotations

from unittest import mock

import pandas as pd
import pytest

from tradingagents.dataflows.vendors.yahoo import market as yahoo_market

NO_BAR = yahoo_market.NO_DAILY_BAR
UNPUBLISHED = f"{NO_BAR} (it may not be published yet)"


def _rows(table: str) -> dict[str, str]:
    """The ``date: value`` rows of an indicator table."""
    rows = {}
    for line in table.splitlines():
        day, sep, value = line.partition(": ")
        if sep and len(day) == 10 and day[4] == day[7] == "-":
            rows[day] = value
    return rows


def _window(values: dict[str, str]) -> dict[str, str]:
    with mock.patch.object(yahoo_market, "_get_stock_stats_bulk", return_value=values):
        return _rows(
            yahoo_market.get_stock_stats_indicators_window("BTC-USD", "rsi", "2026-11-15", 3)
        )


@pytest.mark.unit
def test_the_as_of_date_without_a_bar_reads_as_possibly_unpublished():
    # 00:05 UTC on 11-16: Yahoo's series ends at 11-14, the 11-15 candle is not out.
    rows = _window({"2026-11-12": "41.0", "2026-11-13": "35.5", "2026-11-14": "28.9"})
    assert rows == {
        "2026-11-15": UNPUBLISHED,
        "2026-11-14": "28.9",
        "2026-11-13": "35.5",
        "2026-11-12": "41.0",
    }


@pytest.mark.unit
def test_an_earlier_date_without_a_bar_gives_no_reason():
    rows = _window({"2026-11-12": "41.0", "2026-11-14": "28.9", "2026-11-15": "30.2"})
    assert rows["2026-11-13"] == NO_BAR
    assert rows["2026-11-15"] == "30.2"


@pytest.mark.unit
def test_no_missing_date_is_called_a_closed_market():
    rows = _window({"2026-11-12": "41.0"})
    for value in rows.values():
        assert not any(word in value.lower() for word in ("trading day", "weekend", "holiday"))


@pytest.mark.unit
def test_the_per_day_fallback_marks_the_dates_the_same_way():
    # A failed bulk read sends the window through get_stockstats_indicator, a day at a time.
    def one_day(symbol, indicator, day):
        return {"2026-11-12": "41.0", "2026-11-14": "28.9"}.get(day, NO_BAR)

    with (
        mock.patch.object(yahoo_market, "_get_stock_stats_bulk", side_effect=RuntimeError("boom")),
        mock.patch.object(yahoo_market, "get_stockstats_indicator", side_effect=one_day),
    ):
        table = yahoo_market.get_stock_stats_indicators_window("BTC-USD", "rsi", "2026-11-15", 3)
    assert _rows(table) == {
        "2026-11-15": UNPUBLISHED,
        "2026-11-14": "28.9",
        "2026-11-13": NO_BAR,
        "2026-11-12": "41.0",
    }


@pytest.mark.unit
def test_one_date_without_a_bar_reads_as_no_daily_bar():
    days = pd.date_range("2026-11-01", "2026-11-14")
    frame = pd.DataFrame({
        "Date": days, "Open": 100.0, "High": 101.0, "Low": 99.0,
        "Close": [100.0 + i for i in range(len(days))], "Volume": 1000,
    })
    with mock.patch.object(yahoo_market, "load_ohlcv", side_effect=lambda *a, **k: frame.copy()):
        assert yahoo_market.get_stock_stats("BTC-USD", "close_5_sma", "2026-11-15") == NO_BAR
        assert yahoo_market.get_stock_stats(
            "BTC-USD", "close_5_sma", "2026-11-14"
        ) == pytest.approx(111.0)
