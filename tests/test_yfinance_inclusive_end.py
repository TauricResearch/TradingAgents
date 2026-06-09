"""Regression tests for yfinance's exclusive end-date semantics."""

from unittest import mock

import pandas as pd
import pytest

from tradingagents.dataflows import stockstats_utils, y_finance
from tradingagents.dataflows.config import get_config, set_config


def _history_frame() -> pd.DataFrame:
    dates = pd.to_datetime(["2026-01-05"])
    return pd.DataFrame(
        {
            "Open": [100.0],
            "High": [101.0],
            "Low": [99.0],
            "Close": [100.5],
            "Adj Close": [100.5],
            "Volume": [1_000_000],
        },
        index=dates,
    )


@pytest.mark.unit
def test_get_yfin_data_online_requests_day_after_end_date():
    frame = _history_frame()

    with mock.patch.object(y_finance.yf, "Ticker") as ticker_cls:
        ticker = ticker_cls.return_value
        ticker.history.return_value = frame

        output = y_finance.get_YFin_data_online(
            "AAPL", "2026-01-01", "2026-01-05"
        )

    ticker.history.assert_called_once_with(start="2026-01-01", end="2026-01-06")
    assert "from 2026-01-01 to 2026-01-05" in output


@pytest.mark.unit
def test_load_ohlcv_downloads_through_day_after_cache_end(monkeypatch, tmp_path):
    original_config = get_config()
    set_config({"data_cache_dir": str(tmp_path)})

    real_timestamp = pd.Timestamp
    frame = _history_frame()
    frame.index.name = "Date"

    class FrozenTimestamp:
        def __new__(cls, *args, **kwargs):
            return real_timestamp(*args, **kwargs)

        @staticmethod
        def today():
            return real_timestamp("2026-01-05")

    monkeypatch.setattr(stockstats_utils.pd, "Timestamp", FrozenTimestamp)

    try:
        with mock.patch.object(
            stockstats_utils.yf, "download", return_value=frame
        ) as download:
            data = stockstats_utils.load_ohlcv("AAPL", "2026-01-05")
    finally:
        set_config(original_config)

    kwargs = download.call_args.kwargs
    assert kwargs["end"] == "2026-01-06"
    assert data["Date"].max() == real_timestamp("2026-01-05")
