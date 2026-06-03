import importlib
import sys
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
