"""Tests for the deterministic market-data verification snapshot (#830/#881)."""

from __future__ import annotations

import pandas as pd
import pytest

import tradingagents.dataflows.vendors.yahoo.snapshot as validator
from tradingagents.dataflows.errors import NoMarketDataError


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
        with pytest.raises(NoMarketDataError):
            validator.build_verified_market_snapshot("COF", "2020-01-01")

    def test_raises_on_empty_data(self, monkeypatch):
        monkeypatch.setattr(validator, "load_ohlcv", lambda s, d, fill_gaps=True: pd.DataFrame())
        with pytest.raises(NoMarketDataError):
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


@pytest.mark.unit
class TestPricesKeepTheirDigits:
    """A price prints with its significant digits: a sub-cent coin is not 0.00, a rate keeps its pips."""

    @pytest.mark.parametrize("value, text", [
        (0.00000503123456, "0.00000503123"),
        (1.123456, "1.12346"),
        (763.960022, "763.96"),
        (81074.1875, "81074.19"),
        (100.0, "100.00"),
        (-0.0012345678, "-0.00123457"),
        (0.0, "0.00"),
    ])
    def test_price_text(self, value, text):
        from tradingagents.dataflows.vendors.yahoo.common import price_text
        assert price_text(value) == text

    def test_the_snapshot_shows_a_sub_cent_close(self, monkeypatch):
        data = _sample_ohlcv()
        for col in ("Open", "High", "Low", "Close"):
            data[col] = data[col] * 0.0000001
        monkeypatch.setattr(validator, "load_ohlcv", lambda s, d, fill_gaps=True: data)
        text = validator.build_verified_market_snapshot("SHIB-USD", "2026-05-20")
        assert "| Close | 0.0000135 |" in text and "| Close | 0.00 |" not in text

    def test_the_price_table_shows_a_sub_cent_close(self, monkeypatch):
        from tradingagents.dataflows.vendors.yahoo import market

        days = pd.bdate_range("2026-05-11", "2026-05-15")
        frame = pd.DataFrame({"Open": 0.00000501, "High": 0.00000512, "Low": 0.00000499,
                              "Close": 0.00000503, "Volume": 10**9}, index=days)

        class _Ticker:
            def __init__(self, symbol):
                pass

            def history(self, **kwargs):
                return frame

        monkeypatch.setattr(market.yf, "Ticker", _Ticker)
        text = market.get_YFin_data_online("SHIB-USD", "2026-05-11", "2026-05-15")
        assert "0.00000503" in text and ",0.0," not in text
