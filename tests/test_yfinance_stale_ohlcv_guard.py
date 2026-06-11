from __future__ import annotations

import pandas as pd
import pytest

import tradingagents.dataflows.y_finance as y_finance
from tradingagents.dataflows.stockstats_utils import (
    StaleMarketDataError,
    _assert_ohlcv_not_stale,
)


def test_ohlcv_stale_guard_accepts_recent_prior_trading_day():
    data = pd.DataFrame(
        {
            "Date": [pd.Timestamp("2026-06-10")],
            "Open": [330.0],
            "High": [332.0],
            "Low": [328.0],
            "Close": [330.58],
            "Volume": [1000000],
        }
    )

    _assert_ohlcv_not_stale(data, "2026-06-11", "CB")


def test_ohlcv_stale_guard_rejects_one_year_old_same_month_day():
    data = pd.DataFrame(
        {
            "Date": [pd.Timestamp("2025-06-11")],
            "Open": [280.0],
            "High": [286.0],
            "Low": [278.0],
            "Close": [284.45],
            "Volume": [1000000],
        }
    )

    with pytest.raises(StaleMarketDataError) as exc_info:
        _assert_ohlcv_not_stale(data, "2026-06-11", "CB")

    message = str(exc_info.value)

    assert "Latest OHLCV row for CB is stale" in message
    assert "2025-06-11" in message
    assert "2026-06-11" in message


def test_ohlcv_stale_guard_rejects_empty_data():
    data = pd.DataFrame(columns=["Date", "Open", "High", "Low", "Close", "Volume"])

    with pytest.raises(StaleMarketDataError) as exc_info:
        _assert_ohlcv_not_stale(data, "2026-06-11", "INCY")

    assert "No OHLCV rows available" in str(exc_info.value)


def test_get_yfin_data_online_returns_stale_data_message(monkeypatch):
    stale_data = pd.DataFrame(
        {
            "Open": [280.0],
            "High": [286.0],
            "Low": [278.0],
            "Close": [284.45],
            "Volume": [1000000],
        },
        index=pd.DatetimeIndex([pd.Timestamp("2025-06-11")], name="Date"),
    )

    class DummyTicker:
        def __init__(self, symbol):
            self.symbol = symbol

        def history(self, start, end):
            return stale_data

    monkeypatch.setattr(y_finance.yf, "Ticker", DummyTicker)

    result = y_finance.get_YFin_data_online(
        "CB",
        "2026-06-01",
        "2026-06-11",
    )

    assert "Stale market data for symbol 'CB'" in result
    assert "2025-06-11" in result
    assert "2026-06-11" in result