from __future__ import annotations

import pandas as pd

import tradingagents.dataflows.market_data_validator as validator


def _sample_ohlcv() -> pd.DataFrame:
    dates = pd.bdate_range("2026-04-01", "2026-05-20")
    closes = [100 + i for i in range(len(dates))]

    return pd.DataFrame(
        {
            "Date": dates,
            "Open": [value - 0.5 for value in closes],
            "High": [value + 1.0 for value in closes],
            "Low": [value - 1.0 for value in closes],
            "Close": closes,
            "Volume": [1_000_000 + i for i in range(len(dates))],
        }
    )


def test_verified_market_snapshot_filters_future_rows(monkeypatch):
    data = _sample_ohlcv()

    future_row = pd.DataFrame(
        {
            "Date": [pd.Timestamp("2026-06-01")],
            "Open": [999.0],
            "High": [999.0],
            "Low": [999.0],
            "Close": [999.0],
            "Volume": [999],
        }
    )

    data = pd.concat([data, future_row], ignore_index=True)

    monkeypatch.setattr(
        validator,
        "load_ohlcv",
        lambda symbol, curr_date: data,
    )

    snapshot = validator.build_verified_market_snapshot("COF", "2026-05-13")

    assert "Verified market data snapshot for COF" in snapshot
    assert "Requested analysis date: 2026-05-13" in snapshot
    assert "Latest trading row used: 2026-05-13" in snapshot
    assert "boll_lb" in snapshot
    assert "999.00" not in snapshot


def test_verified_market_snapshot_uses_previous_trading_day(monkeypatch):
    data = _sample_ohlcv()

    monkeypatch.setattr(
        validator,
        "load_ohlcv",
        lambda symbol, curr_date: data,
    )

    snapshot = validator.build_verified_market_snapshot("COF", "2026-05-16")

    assert "Requested analysis date: 2026-05-16" in snapshot
    assert "Latest trading row used: 2026-05-15" in snapshot
    assert "Recent verified closes" in snapshot