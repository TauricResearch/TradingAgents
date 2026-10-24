"""Sub-cent price rendering: prices below one must not render as zero (#1567)."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

import tradingagents.dataflows.vendors.yahoo.market as market
import tradingagents.dataflows.vendors.yahoo.snapshot as snapshot


def _sub_cent_ohlcv() -> pd.DataFrame:
    return pd.DataFrame({
        "Date": pd.to_datetime(["2026-10-20", "2026-10-21"]),
        "Open": [0.0029, 0.0038], "High": [0.0032, 0.0042],
        "Low": [0.0028, 0.0037], "Close": [0.0030, 0.0040],
        "Volume": [1_000_000, 1_200_000],
    })


@pytest.mark.unit
class TestSubCentPriceRendering:
    def test_render_price_precision_keeps_sub_cent_digits(self):
        assert market._render_price_precision(0.0030) == 0.003
        assert market._render_price_precision(0.0040) == 0.004
        assert market._render_price_precision(0.0029) == 0.0029
        # Normal prices keep the 2-decimal display.
        assert market._render_price_precision(250.123) == 250.12
        assert market._render_price_precision(1.0) == 1.0

    def test_csv_close_table_preserves_sub_cent_moves(self):
        rows = _sub_cent_ohlcv()

        class OfflineTicker:
            def __init__(self, symbol):
                pass

            def history(self, **kwargs):
                return rows.set_index("Date").copy()

        with patch.object(market.yf, "Ticker", OfflineTicker):
            prices = market.get_YFin_data_online("PENNY", "2026-10-20", "2026-10-21")

        assert "2026-10-20,0.0029,0.0032,0.0028,0.003,1000000" in prices
        assert "2026-10-21,0.0038,0.0042,0.0037,0.004,1200000" in prices
        # The 33% close-to-close move must survive rendering.
        assert ",0.0,0.0,0.0,0.0," not in prices

    def test_snapshot_preserves_sub_cent_prices(self):
        rows = _sub_cent_ohlcv()
        with patch.object(snapshot, "load_ohlcv", return_value=rows.copy()):
            snap = snapshot.build_verified_market_snapshot(
                "PENNY", "2026-10-21", look_back_days=2, indicators=["close_10_ema"],
            )
        assert "| Close | 0.004 |" in snap
        assert "| 2026-10-20 | 0.003 |" in snap
        assert "| 2026-10-21 | 0.004 |" in snap
        assert "0.00 |" not in snap.replace("| Close | 0.004 |", "")

    def test_snapshot_normal_prices_stay_two_decimals(self):
        dates = pd.bdate_range("2026-04-01", "2026-05-20")
        closes = [100 + i for i in range(len(dates))]
        rows = pd.DataFrame({
            "Date": dates,
            "Open": [c - 0.5 for c in closes], "High": [c + 1.0 for c in closes],
            "Low": [c - 1.0 for c in closes], "Close": closes,
            "Volume": [1_000_000 + i for i in range(len(dates))],
        })
        with patch.object(snapshot, "load_ohlcv", return_value=rows.copy()):
            snap = snapshot.build_verified_market_snapshot("COF", "2026-05-13")
        assert "| Close | 130 |" in snap  # integer close renders exactly (no float coercion)
