from curl_cffi.requests.exceptions import SSLError as CurlCffiSSLError
import pandas as pd

from tradingagents.dataflows import y_finance


def test_get_yfin_data_online_uses_cached_ohlcv_when_history_raises_curl_cffi(monkeypatch):
    class FailingTicker:
        def __init__(self, symbol):
            self.symbol = symbol

        def history(self, **kwargs):
            raise CurlCffiSSLError("curl TLS failed")

    cached = pd.DataFrame(
        [
            {
                "Date": pd.Timestamp("2026-01-02"),
                "Open": 10.0,
                "High": 11.0,
                "Low": 9.0,
                "Close": 10.5,
                "Volume": 1000,
            },
            {
                "Date": pd.Timestamp("2026-01-05"),
                "Open": 10.5,
                "High": 11.5,
                "Low": 10.0,
                "Close": 11.0,
                "Volume": 1100,
            },
        ]
    )

    monkeypatch.setattr(y_finance.yf, "Ticker", FailingTicker)
    monkeypatch.setattr(y_finance, "load_ohlcv", lambda symbol, curr_date: cached)

    result = y_finance.get_YFin_data_online("002396.SZ", "2026-01-01", "2026-01-31")

    assert "# Stock data for 002396.SZ from 2026-01-01 to 2026-01-31" in result
    assert "# Source: yfinance cache" in result
    assert "# Total records: 2" in result
    assert "2026-01-02" in result
