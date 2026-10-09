"""A missing price row does not establish that an exchange was closed."""

from types import SimpleNamespace

import pandas as pd
import pytest

from tradingagents.agents import tools
from tradingagents.dataflows import router
from tradingagents.dataflows.vendors.yahoo import market, ohlcv


@pytest.mark.unit
@pytest.mark.parametrize("bulk_fails", [False, True], ids=["bulk", "per-day-fallback"])
def test_an_unsettled_weekday_is_not_reported_as_an_exchange_holiday(
    monkeypatch, tmp_path, bulk_fails
):
    # This is the input already supported by the latest-bar loader: keep the
    # last usable close when the vendor's newest row has no closing price.
    frame = pd.DataFrame({
        "Date": pd.to_datetime(["2026-05-07", "2026-05-08"]),
        "Open": [100.0, 101.0], "High": [101.0, 102.0], "Low": [99.0, 100.0],
        "Close": [100.0, float("nan")], "Volume": [1000, 1000],
    })
    monkeypatch.setattr(ohlcv, "get_config", lambda: {"data_cache_dir": str(tmp_path)})
    monkeypatch.setattr(ohlcv, "_cache_is_fresh", lambda *args: True)
    monkeypatch.setattr(
        ohlcv.yf, "Ticker",
        lambda symbol: SimpleNamespace(history=lambda **kwargs: frame.set_index("Date")),
    )
    monkeypatch.setattr(router, "get_vendor", lambda *args: "yfinance")
    if bulk_fails:
        def fail_bulk(*args):
            raise RuntimeError("bulk calculation failed")

        monkeypatch.setattr(market, "_get_stock_stats_bulk", fail_bulk)

    out = tools.get_indicators.func("AAPL", "close_50_sma", "2026-05-08", 1)
    single = market.get_stockstats_indicator("AAPL", "close_50_sma", "2026-05-08")

    assert "2026-05-08: N/A: No usable price row for this date" in out
    assert single == "N/A: No usable price row for this date"
    assert "Not a trading day" not in out + single
    assert "2026-05-07: 100.0" in out
    assert market.get_stockstats_indicator("AAPL", "close_50_sma", "2026-05-07") == "100.0"


@pytest.mark.unit
@pytest.mark.parametrize("requested", ["2026-05-08", "2026-05-09"], ids=["missing-weekday", "weekend"])
def test_dates_without_rows_remain_listed_as_unavailable(monkeypatch, requested):
    frame = pd.DataFrame({
        "Date": pd.to_datetime(["2026-05-07"]),
        "Open": [100.0], "High": [101.0], "Low": [99.0],
        "Close": [100.0], "Volume": [1000],
    })
    monkeypatch.setattr(market, "load_ohlcv", lambda *args: frame.copy())

    out = market.get_stock_stats_indicators_window("AAPL", "close_50_sma", requested, 2)
    assert f"{requested}: N/A: No usable price row for this date" in out
    assert "2026-05-07: 100.0" in out
    assert "Not a trading day" not in out
