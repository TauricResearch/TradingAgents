import pandas as pd

from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.crypto_data import get_crypto_indicator, get_crypto_ohlcv
from tradingagents.default_config import DEFAULT_CONFIG


def _sample_ohlcv(rows=90):
    dates = pd.date_range("2026-01-01", periods=rows, freq="15min", tz="UTC")
    close = [100 + i * 0.1 for i in range(rows)]
    return pd.DataFrame(
        {
            "Date": dates,
            "Open": close,
            "High": [value + 1 for value in close],
            "Low": [value - 1 for value in close],
            "Close": close,
            "Volume": [100 + (i % 5) * 10 for i in range(rows)],
        }
    )


def test_get_crypto_ohlcv_accepts_timeframe_override(monkeypatch):
    captured = {}

    def fake_fetch(symbol, since=None, limit=None, timeframe=None):
        captured["symbol"] = symbol
        captured["timeframe"] = timeframe
        return _sample_ohlcv()

    monkeypatch.setattr("tradingagents.dataflows.crypto_data._fetch_ohlcv", fake_fetch)
    set_config({"crypto_timeframe": "15m", "crypto_report_rows": 5})
    try:
        output = get_crypto_ohlcv("BTC/USDT", "", "", timeframe="1h")
    finally:
        set_config(DEFAULT_CONFIG.copy())

    assert captured == {"symbol": "BTC/USDT", "timeframe": "1h"}
    assert "Binance BTC/USDT OHLCV (1h)" in output


def test_get_crypto_indicator_accepts_timeframe_override(monkeypatch):
    captured = {}

    def fake_fetch(symbol, since=None, limit=None, timeframe=None):
        captured["symbol"] = symbol
        captured["timeframe"] = timeframe
        return _sample_ohlcv()

    monkeypatch.setattr("tradingagents.dataflows.crypto_data._fetch_ohlcv", fake_fetch)
    set_config({"crypto_timeframe": "15m", "crypto_indicator_rows": 5, "crypto_ohlcv_limit": 90})
    try:
        output = get_crypto_indicator("ETH/USDT", "rsi", "2026-01-02", look_back_days=1, timeframe="30m")
    finally:
        set_config(DEFAULT_CONFIG.copy())

    assert captured == {"symbol": "ETH/USDT", "timeframe": "30m"}
    assert "Binance ETH/USDT rsi (30m)" in output
