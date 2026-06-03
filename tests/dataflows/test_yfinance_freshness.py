import importlib
import os
import sys
import time
from types import ModuleType
from unittest.mock import MagicMock

import pandas as pd
import pytest

from tradingagents.dataflows.market_snapshot import MarketDataUnavailable


def _load_yfinance_module(monkeypatch, ticker):
    fake_yfinance = ModuleType("yfinance")
    fake_yfinance.Ticker = MagicMock(return_value=ticker)
    fake_yfinance.download = MagicMock()

    fake_exceptions = ModuleType("yfinance.exceptions")
    fake_exceptions.YFRateLimitError = type("YFRateLimitError", (Exception,), {})
    fake_stockstats = ModuleType("stockstats")
    fake_stockstats.wrap = lambda data: data

    monkeypatch.setitem(sys.modules, "yfinance", fake_yfinance)
    monkeypatch.setitem(sys.modules, "yfinance.exceptions", fake_exceptions)
    monkeypatch.setitem(sys.modules, "stockstats", fake_stockstats)
    sys.modules.pop("tradingagents.dataflows.y_finance", None)
    sys.modules.pop("tradingagents.dataflows.stockstats_utils", None)
    return importlib.import_module("tradingagents.dataflows.y_finance")


def _load_stockstats_utils(monkeypatch):
    fake_yfinance = ModuleType("yfinance")
    fake_yfinance.Ticker = MagicMock()
    fake_yfinance.download = MagicMock()

    fake_exceptions = ModuleType("yfinance.exceptions")
    fake_exceptions.YFRateLimitError = type("YFRateLimitError", (Exception,), {})

    fake_stockstats = ModuleType("stockstats")
    fake_stockstats.wrap = lambda data: data

    monkeypatch.setitem(sys.modules, "yfinance", fake_yfinance)
    monkeypatch.setitem(sys.modules, "yfinance.exceptions", fake_exceptions)
    monkeypatch.setitem(sys.modules, "stockstats", fake_stockstats)
    sys.modules.pop("tradingagents.dataflows.stockstats_utils", None)
    return importlib.import_module("tradingagents.dataflows.stockstats_utils")


def test_yfinance_stock_data_uses_inclusive_date_end(monkeypatch):

    df = pd.DataFrame(
        {
            "Open": [100.0],
            "High": [101.0],
            "Low": [99.0],
            "Close": [100.5],
            "Volume": [1000],
        },
        index=pd.DatetimeIndex([pd.Timestamp("2026-06-03")]),
    )
    history = MagicMock(return_value=df)
    ticker = MagicMock(history=history)
    yfmod = _load_yfinance_module(monkeypatch, ticker)

    payload = yfmod.get_YFin_data_online("AAPL", "2026-06-01", "2026-06-03")

    history.assert_called_once_with(start="2026-06-01", end="2026-06-04")
    assert "2026-06-03" in payload


def test_yfinance_stock_data_empty_raises_vendor_error(monkeypatch):
    ticker = MagicMock(history=MagicMock(return_value=pd.DataFrame()))
    yfmod = _load_yfinance_module(monkeypatch, ticker)

    with pytest.raises(MarketDataUnavailable, match="empty"):
        yfmod.get_YFin_data_online("ZZZZ", "2026-06-01", "2026-06-03")


def test_yfinance_market_snapshot_formats_recent_bars(monkeypatch):
    df = pd.DataFrame(
        {
            "Open": [100.0, 101.0],
            "High": [102.0, 103.0],
            "Low": [99.0, 100.0],
            "Close": [101.0, 102.5],
            "Volume": [1000, 1200],
        },
        index=pd.DatetimeIndex(
            [pd.Timestamp("2026-06-02"), pd.Timestamp("2026-06-03")]
        ),
    )
    ticker = MagicMock(history=MagicMock(return_value=df))
    yfmod = _load_yfinance_module(monkeypatch, ticker)

    text = yfmod.get_market_snapshot("AAPL", "2026-06-03", lookback_days=3)

    assert "# Market snapshot for AAPL" in text
    assert "Source: yfinance" in text
    assert "Freshness:" in text
    assert "102.5000" in text


def test_same_day_ohlcv_cache_refreshes_when_stale(tmp_path, monkeypatch):
    utils = _load_stockstats_utils(monkeypatch)

    cache_file = tmp_path / "AAPL-YFin-data-test.csv"
    cache_file.write_text(
        "Date,Open,High,Low,Close,Volume\n2026-06-02,1,1,1,1,1\n",
        encoding="utf-8",
    )
    old_mtime = time.time() - 3600
    os.utime(cache_file, (old_mtime, old_mtime))

    assert utils._should_refresh_cache(
        str(cache_file),
        curr_date_dt=pd.Timestamp("2026-06-03"),
        today_date=pd.Timestamp("2026-06-03"),
        ttl_seconds=900,
    ) is True


def test_same_day_ohlcv_cache_reuses_fresh_file(tmp_path, monkeypatch):
    utils = _load_stockstats_utils(monkeypatch)

    cache_file = tmp_path / "AAPL-YFin-data-test.csv"
    cache_file.write_text(
        "Date,Open,High,Low,Close,Volume\n2026-06-03,2,2,2,2,2\n",
        encoding="utf-8",
    )

    assert utils._should_refresh_cache(
        str(cache_file),
        curr_date_dt=pd.Timestamp("2026-06-03"),
        today_date=pd.Timestamp("2026-06-03"),
        ttl_seconds=900,
    ) is False


def test_past_ohlcv_cache_reuses_file_even_when_old(tmp_path, monkeypatch):
    utils = _load_stockstats_utils(monkeypatch)

    cache_file = tmp_path / "AAPL-YFin-data-test.csv"
    cache_file.write_text(
        "Date,Open,High,Low,Close,Volume\n2026-05-01,2,2,2,2,2\n",
        encoding="utf-8",
    )
    old_mtime = time.time() - 86400
    os.utime(cache_file, (old_mtime, old_mtime))

    assert utils._should_refresh_cache(
        str(cache_file),
        curr_date_dt=pd.Timestamp("2026-05-01"),
        today_date=pd.Timestamp("2026-06-03"),
        ttl_seconds=900,
    ) is False
