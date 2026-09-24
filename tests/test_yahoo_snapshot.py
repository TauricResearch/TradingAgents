"""Tests for the deterministic market-data verification snapshot (#830/#881)."""

from __future__ import annotations

import pandas as pd
import pytest

import tradingagents.dataflows.vendors.yahoo.snapshot as validator


def _sample_ohlcv() -> pd.DataFrame:
    dates = pd.bdate_range("2026-04-01", "2026-05-20")
    closes = [100 + i for i in range(len(dates))]
    return pd.DataFrame({
        "Date": dates,
        "Open": [c - 0.5 for c in closes],
        "High": [c + 1.0 for c in closes],
        "Low": [c - 1.0 for c in closes],
        "Close": closes,
        "Volume": [1_000_000 + i for i in range(len(dates))],
    })


@pytest.mark.unit
class TestVerifiedSnapshot:
    def test_excludes_future_rows(self, monkeypatch):
        data = pd.concat([
            _sample_ohlcv(),
            pd.DataFrame({"Date": [pd.Timestamp("2026-06-01")], "Open": [999.0],
                          "High": [999.0], "Low": [999.0], "Close": [999.0], "Volume": [999]}),
        ], ignore_index=True)
        monkeypatch.setattr(validator, "load_ohlcv", lambda s, d, fill_gaps=True: data)

        snap = validator.build_verified_market_snapshot("COF", "2026-05-13")
        assert "Verified market data snapshot for COF" in snap
        assert "Requested analysis date: 2026-05-13" in snap
        assert "Latest trading row used: 2026-05-13" in snap
        assert "999.00" not in snap          # future row excluded
        assert "boll_lb" in snap             # indicators present

    def test_uses_previous_trading_day_when_date_is_weekend(self, monkeypatch):
        monkeypatch.setattr(validator, "load_ohlcv", lambda s, d, fill_gaps=True: _sample_ohlcv())
        # 2026-05-16 is a Saturday; latest row should be Fri 2026-05-15
        snap = validator.build_verified_market_snapshot("COF", "2026-05-16")
        assert "Latest trading row used: 2026-05-15" in snap
        assert "Recent verified closes" in snap

    def test_raises_when_no_rows_on_or_before_date(self, monkeypatch):
        monkeypatch.setattr(validator, "load_ohlcv", lambda s, d, fill_gaps=True: _sample_ohlcv())
        with pytest.raises(ValueError):
            validator.build_verified_market_snapshot("COF", "2020-01-01")

    def test_raises_on_empty_data(self, monkeypatch):
        monkeypatch.setattr(validator, "load_ohlcv", lambda s, d, fill_gaps=True: pd.DataFrame())
        with pytest.raises(ValueError):
            validator.build_verified_market_snapshot("COF", "2026-05-13")

    def test_look_back_window_capped_at_30(self, monkeypatch):
        monkeypatch.setattr(validator, "load_ohlcv", lambda s, d, fill_gaps=True: _sample_ohlcv())
        snap = validator.build_verified_market_snapshot("COF", "2026-05-20", look_back_days=999)
        # last-N closes table has at most 30 data rows
        close_rows = [ln for ln in snap.splitlines() if ln.startswith("| 2026-")]
        assert 0 < len(close_rows) <= 30


@pytest.mark.unit
class TestTool:
    def test_tool_delegates_to_builder(self, monkeypatch):
        from tradingagents.agents.tools import get_verified_market_snapshot
        monkeypatch.setattr(validator, "load_ohlcv", lambda s, d, fill_gaps=True: _sample_ohlcv())
        out = get_verified_market_snapshot.invoke(
            {"symbol": "COF", "curr_date": "2026-05-20"}
        )
        assert "Verified market data snapshot for COF" in out

    def test_tool_handles_no_market_data_error(self, monkeypatch):
        from tradingagents.agents.tools import get_verified_market_snapshot
        from tradingagents.dataflows.errors import NoMarketDataError

        def _raise(*args, **kwargs):
            raise NoMarketDataError("COF", "COF", "no price rows")

        monkeypatch.setattr(validator, "load_ohlcv", _raise)
        out = get_verified_market_snapshot.invoke(
            {"symbol": "COF", "curr_date": "2026-05-20"}
        )
        assert "NO_DATA_AVAILABLE" in out
        assert "COF" in out

    def test_tool_handles_vendor_rate_limit_error(self, monkeypatch):
        from tradingagents.agents.tools import get_verified_market_snapshot
        from tradingagents.dataflows.errors import VendorRateLimitError

        def _raise(*args, **kwargs):
            raise VendorRateLimitError("Throttled by Yahoo")

        monkeypatch.setattr(validator, "load_ohlcv", _raise)
        out = get_verified_market_snapshot.invoke(
            {"symbol": "COF", "curr_date": "2026-05-20"}
        )
        assert "DATA_UNAVAILABLE" in out
        assert "rate-limited" in out

    def test_tool_handles_value_error(self, monkeypatch):
        from tradingagents.agents.tools import get_verified_market_snapshot

        def _raise(*args, **kwargs):
            raise ValueError("No rows available")

        monkeypatch.setattr(validator, "load_ohlcv", _raise)
        out = get_verified_market_snapshot.invoke(
            {"symbol": "COF", "curr_date": "2026-05-20"}
        )
        assert "NO_DATA_AVAILABLE" in out

    def test_tool_handles_generic_exception(self, monkeypatch):
        from tradingagents.agents.tools import get_verified_market_snapshot

        def _raise(*args, **kwargs):
            raise RuntimeError("Unexpected failure")

        monkeypatch.setattr(validator, "load_ohlcv", _raise)
        out = get_verified_market_snapshot.invoke(
            {"symbol": "COF", "curr_date": "2026-05-20"}
        )
        assert "DATA_UNAVAILABLE" in out

