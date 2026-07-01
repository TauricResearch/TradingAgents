"""Tests for the multi-timeframe Z-Score (20-period close z-score) indicator.

Rolling close z-score (signed: + above mean / overbought, - below / oversold),
the weekly/monthly/daily tiering payload, the report formatter, and the wiring
into the yfinance indicator window + the Alpha Vantage fallback signal.

No network: pure functions take hand-built frames; the window test
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
class TestComputeZscore:
    def test_short_history_is_zero(self):
        # Fewer than `window` bars: no full window yet -> 0 (no signal).
        close = pd.Series([1.0, 2.0, 3.0])
        assert list(su.compute_zscore(close, window=20)) == [0.0, 0.0, 0.0]

    def test_flat_window_is_zero(self):
        # std == 0 over the window -> divide-by-zero guard yields 0.
        close = pd.Series([5.0] * 25)
        assert su.compute_zscore(close, window=20).iloc[-1] == 0.0

    def test_last_value_matches_manual_formula(self):
        # (close - rolling mean) / rolling sample std over the trailing window.
        close = pd.Series([float(i) for i in range(1, 26)])
        window = 20
        tail = close.iloc[-window:]
        expected = (close.iloc[-1] - tail.mean()) / tail.std()
        assert su.compute_zscore(close, window).iloc[-1] == pytest.approx(expected)

    def test_above_mean_is_positive(self):
        close = pd.Series([10.0] * 19 + [20.0])  # last bar spikes above the mean
        assert su.compute_zscore(close, window=20).iloc[-1] > 0

    def test_below_mean_is_negative(self):
        close = pd.Series([10.0] * 19 + [1.0])  # last bar drops below the mean
        assert su.compute_zscore(close, window=20).iloc[-1] < 0

    def test_preserves_input_index(self):
        idx = pd.date_range("2026-01-01", periods=25, freq="D")
        close = pd.Series([float(i) for i in range(25)], index=idx)
        assert list(su.compute_zscore(close).index) == list(idx)


@pytest.mark.unit
class TestZscoreByTimeframe:
    def test_returns_all_three_float_keys(self):
        z = su.zscore_by_timeframe(_ohlcv([100 + i for i in range(320)]))
        assert set(z) == {"weekly", "monthly", "daily"}
        assert all(isinstance(v, float) for v in z.values())

    def test_rising_series_is_above_mean(self):
        # A steadily rising series sits above its trailing mean on daily bars.
        z = su.zscore_by_timeframe(_ohlcv([100 + i for i in range(320)]))
        assert z["daily"] > 0

    def test_falling_series_is_below_mean(self):
        z = su.zscore_by_timeframe(_ohlcv([500 - i for i in range(320)]))
        assert z["daily"] < 0

    def test_curr_date_excludes_future_bars(self):
        # A late spike must not leak in when curr_date predates it.
        df = _ohlcv([100.0] * 30 + [1000.0] * 5)
        cutoff = df["Date"].iloc[29].strftime("%Y-%m-%d")
        z = su.zscore_by_timeframe(df, cutoff)
        assert z["daily"] == 0.0  # flat history up to cutoff -> no signal

    def test_empty_frame_is_zero(self):
        empty = pd.DataFrame({"Date": [], "Close": []})
        assert su.zscore_by_timeframe(empty) == {
            "weekly": 0.0,
            "monthly": 0.0,
            "daily": 0.0,
        }


@pytest.mark.unit
class TestFormatZscoreBlock:
    def test_lists_three_tiers_with_signed_values(self):
        block = su.format_zscore_block({"weekly": 2.5, "monthly": -1.4, "daily": 0.2})
        for token in ("Tier 1", "Tier 2", "Tier 3", "Weekly", "Monthly", "Daily"):
            assert token in block
        assert "+2.50" in block and "-1.40" in block and "+0.20" in block

    def test_stretched_reading_is_flagged(self):
        block = su.format_zscore_block({"weekly": 2.5, "monthly": 0.0, "daily": 0.0})
        assert "overbought" in block
        block = su.format_zscore_block({"weekly": -2.5, "monthly": 0.0, "daily": 0.0})
        assert "oversold" in block

    def test_near_zero_reads_as_near_the_mean(self):
        block = su.format_zscore_block({"weekly": 0.0, "monthly": 0.0, "daily": 0.0})
        assert "near the mean" in block


@pytest.mark.unit
class TestYFinanceWindowWiring:
    def test_z_score_returns_tiered_block_without_valueerror(self, monkeypatch):
        """`z_score` is a legal indicator name in the yfinance window and emits
        the three-tier block — it must NOT raise the "not supported" ValueError
        that unknown names trigger."""
        from tradingagents.dataflows import y_finance

        frame = _ohlcv([100 + i for i in range(320)])
        monkeypatch.setattr(y_finance, "load_ohlcv", lambda symbol, curr_date: frame)

        out = y_finance.get_stock_stats_indicators_window(
            "AAPL", "z_score", "2026-06-04", 30
        )
        for token in ("Tier 1", "Tier 2", "Tier 3", "Weekly", "Monthly", "Daily"):
            assert token in out

    def test_unknown_indicator_still_raises(self):
        from tradingagents.dataflows import y_finance

        with pytest.raises(ValueError):
            y_finance.get_stock_stats_indicators_window(
                "AAPL", "not_an_indicator", "2026-06-04", 30
            )


@pytest.mark.unit
class TestAlphaVantageFallback:
    def test_z_score_raises_so_router_falls_back_to_yfinance(self):
        """Alpha Vantage has no z-score endpoint. `z_score` raises the standard
        "not supported" ValueError; route_to_vendor's catch-all then falls
        through to yfinance (which computes it from OHLCV)."""
        from tradingagents.dataflows import alpha_vantage_indicator as av

        with pytest.raises(ValueError):
            av.get_indicator("AAPL", "z_score", "2026-06-04", 30)

    def test_route_to_vendor_falls_back_to_yfinance(self, monkeypatch):
        """End-to-end: with Alpha Vantage forced primary, a z_score call still
        returns the real tiered block computed by yfinance."""
        import copy

        from tradingagents.dataflows import interface, y_finance
        from tradingagents.dataflows.config import get_config, set_config

        frame = _ohlcv([100 + i for i in range(320)])  # rising -> above mean
        monkeypatch.setattr(y_finance, "load_ohlcv", lambda symbol, curr_date: frame)

        saved = copy.deepcopy(get_config())  # restore so global config doesn't leak
        try:
            cfg = get_config()
            cfg.setdefault("tool_vendors", {})["get_indicators"] = "alpha_vantage,yfinance"
            set_config(cfg)

            out = interface.route_to_vendor(
                "get_indicators", "AAPL", "z_score", "2026-06-04", 30
            )
            assert "Tier 1 Weekly" in out
        finally:
            set_config(saved)
