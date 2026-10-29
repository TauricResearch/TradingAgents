from __future__ import annotations

import pandas as pd
import pytest

import tradingagents.dataflows.market_scan as scanner
from tradingagents.dataflows.errors import NoMarketDataError


@pytest.mark.unit
def test_scan_returns_latest_close_and_change_without_future_rows(monkeypatch):
    data = pd.DataFrame({
        "Date": pd.to_datetime(["2026-10-26", "2026-10-27", "2026-10-29"]),
        "Close": [100.0, 105.0, 500.0],
        "Volume": [1000, 1200, 9999],
    })
    monkeypatch.setattr(scanner, "load_ohlcv", lambda *args, **kwargs: data)

    result = scanner.scan_market_data("BTCUSD", "2026-10-28")

    assert result.requested_symbol == "BTCUSD"
    assert result.symbol == "BTC-USD"
    assert result.latest_date == "2026-10-27"
    assert result.close == 105.0
    assert result.change_percent == 5.0
    assert result.volume == 1200


@pytest.mark.unit
def test_scan_reports_missing_daily_data(monkeypatch):
    monkeypatch.setattr(scanner, "load_ohlcv", lambda *args, **kwargs: pd.DataFrame())

    with pytest.raises(NoMarketDataError, match="no usable daily OHLCV"):
        scanner.scan_market_data("UNKNOWN", "2026-10-28")


@pytest.mark.unit
def test_scan_rejects_unsafe_symbol_before_fetch(monkeypatch):
    monkeypatch.setattr(
        scanner, "load_ohlcv", lambda *args, **kwargs: pytest.fail("unsafe symbol was fetched")
    )

    with pytest.raises(ValueError, match="ticker contains characters"):
        scanner.scan_market_data("../secret", "2026-10-28")
