"""Tests for the multi-timeframe SuperTrend indicator.

stockstats computes the SuperTrend line itself (14-period ATR, 3x multiplier);
the custom layer resamples OHLCV to weekly/monthly bars and reports per-tier
direction, trailing-stop level and distance — mirroring the TD-9 and z-score
tiering. No network: pure functions take hand-built frames; the window test
monkeypatches ``load_ohlcv``. Mirrors ``tests/test_td_sequential.py``.
"""

from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.dataflows import stockstats_utils as su


def _ohlcv(closes, end="2026-06-04"):
    """OHLCV frame of ``len(closes)`` business days ending at ``end``."""
    dates = pd.bdate_range(end=end, periods=len(closes))
    closes = [float(c) for c in closes]
    return pd.DataFrame(
        {
            "Date": dates,
            "Open": closes,
            "High": [c + 1 for c in closes],
            "Low": [c - 1 for c in closes],
            "Close": closes,
            "Volume": [1_000_000] * len(closes),
        }
    )


@pytest.mark.unit
class TestSupertrendByTimeframe:
    def test_returns_all_three_tier_keys(self):
        snaps = su.supertrend_by_timeframe(_ohlcv([100 + i for i in range(320)]))
        assert set(snaps) == {"weekly", "monthly", "daily"}

    def test_uptrend_has_stop_below_close_on_all_tiers(self):
        snaps = su.supertrend_by_timeframe(_ohlcv([100 + i for i in range(320)]))
        for tier, snap in snaps.items():
            assert snap is not None, f"{tier} tier missing"
            assert snap["direction"] == "up"
            assert snap["level"] > 0
            assert snap["distance_pct"] > 0  # close sits above the stop

    def test_downtrend_has_stop_above_close(self):
        snaps = su.supertrend_by_timeframe(_ohlcv([800 - i * 2 for i in range(320)]))
        assert snaps["daily"]["direction"] == "down"
        assert snaps["daily"]["distance_pct"] < 0

    def test_curr_date_excludes_future_bars(self):
        # A crash after the cutoff must not flip the trend read at the cutoff.
        df = _ohlcv([100 + i for i in range(300)] + [10.0] * 20)
        cutoff = df["Date"].iloc[299].strftime("%Y-%m-%d")
        snaps = su.supertrend_by_timeframe(df, cutoff)
        assert snaps["daily"]["direction"] == "up"

    def test_short_history_is_none(self):
        snaps = su.supertrend_by_timeframe(_ohlcv([100.0]))
        assert snaps["daily"] is None

    def test_empty_frame_is_all_none(self):
        empty = pd.DataFrame(
            {"Date": [], "Open": [], "High": [], "Low": [], "Close": [], "Volume": []}
        )
        assert su.supertrend_by_timeframe(empty) == {
            "weekly": None,
            "monthly": None,
            "daily": None,
        }


@pytest.mark.unit
class TestFormatSupertrendBlock:
    def test_lists_three_tiers_with_direction_and_stop(self):
        block = su.format_supertrend_block(
            {
                "weekly": {"direction": "up", "level": 123.45, "distance_pct": 4.5},
                "monthly": {"direction": "down", "level": 150.0, "distance_pct": -2.25},
                "daily": {"direction": "up", "level": 130.0, "distance_pct": 0.8},
            }
        )
        for token in ("Tier 1", "Tier 2", "Tier 3", "Weekly", "Monthly", "Daily"):
            assert token in block
        assert "UP — trailing stop 123.45" in block
        assert "DOWN — trailing stop 150.00" in block
        assert "+4.50%" in block and "-2.25%" in block

    def test_missing_tier_reads_as_insufficient_history(self):
        block = su.format_supertrend_block({"weekly": None, "monthly": None, "daily": None})
        assert block.count("insufficient history") == 3


@pytest.mark.unit
class TestYFinanceWindowWiring:
    def test_supertrend_returns_tiered_block_without_valueerror(self, monkeypatch):
        from tradingagents.dataflows import y_finance

        frame = _ohlcv([100 + i for i in range(320)])
        monkeypatch.setattr(y_finance, "load_ohlcv", lambda symbol, curr_date: frame)

        out = y_finance.get_stock_stats_indicators_window(
            "AAPL", "supertrend", "2026-06-04", 30
        )
        for token in ("Tier 1", "Tier 2", "Tier 3", "trailing stop", "SuperTrend"):
            assert token in out


@pytest.mark.unit
class TestAlphaVantageFallback:
    def test_supertrend_raises_so_router_falls_back_to_yfinance(self):
        from tradingagents.dataflows import alpha_vantage_indicator as av

        with pytest.raises(ValueError):
            av.get_indicator("AAPL", "supertrend", "2026-06-04", 30)
