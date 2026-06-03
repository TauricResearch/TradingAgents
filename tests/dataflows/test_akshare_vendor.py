from types import SimpleNamespace

import pandas as pd
import pytest

from tradingagents.dataflows.market_snapshot import MarketDataUnavailable


def test_akshare_us_daily_formats_stock_data(monkeypatch):
    import tradingagents.dataflows.akshare as akmod

    fake_ak = SimpleNamespace(
        stock_us_daily=lambda symbol, adjust="": pd.DataFrame(
            {
                "date": ["2026-06-02", "2026-06-03"],
                "open": [100.0, 101.0],
                "high": [102.0, 103.0],
                "low": [99.0, 100.0],
                "close": [101.0, 102.5],
                "volume": [1000, 1200],
            }
        )
    )
    monkeypatch.setattr(akmod, "_ak", lambda: fake_ak)

    text = akmod.get_stock_data("AAPL", "2026-06-01", "2026-06-03")

    assert "# Stock data for AAPL from 2026-06-01 to 2026-06-03" in text
    assert "2026-06-03" in text
    assert "102.5" in text


def test_akshare_china_a_share_symbol_mapping(monkeypatch):
    import tradingagents.dataflows.akshare as akmod

    captured = {}

    def stock_zh_a_hist(symbol, period, start_date, end_date, adjust=""):
        captured.update(
            {
                "symbol": symbol,
                "period": period,
                "start_date": start_date,
                "end_date": end_date,
            }
        )
        return pd.DataFrame(
            {
                "日期": ["2026-06-03"],
                "开盘": [10.0],
                "最高": [11.0],
                "最低": [9.0],
                "收盘": [10.5],
                "成交量": [10000],
            }
        )

    fake_ak = SimpleNamespace(stock_zh_a_hist=stock_zh_a_hist)
    monkeypatch.setattr(akmod, "_ak", lambda: fake_ak)

    text = akmod.get_market_snapshot("600519.SS", "2026-06-03")

    assert captured == {
        "symbol": "600519",
        "period": "daily",
        "start_date": "20260524",
        "end_date": "20260603",
    }
    assert "Source: akshare" in text
    assert "10.5000" in text


def test_akshare_unsupported_symbol_raises():
    import tradingagents.dataflows.akshare as akmod

    with pytest.raises(MarketDataUnavailable, match="unsupported"):
        akmod.get_stock_data("BTC-USD", "2026-06-01", "2026-06-03")
