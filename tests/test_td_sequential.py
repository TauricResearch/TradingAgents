"""Tests for multi-timeframe TD-9 (TD Sequential Setup) indicator (plan P1).

TD Setup running count, signed by direction (+ buy-setup, - sell-setup), the
weekly/monthly/daily tiering payload, the report formatter, and the wiring into
the yfinance indicator window + the Alpha Vantage fallback signal.

No network: pure functions take hand-built frames; the window test monkeypatches
``load_ohlcv``. Mirrors the style of ``tests/test_stockstats_date_column.py``.
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
class TestComputeTdSetup:
    def test_buy_setup_reports_running_count_of_seven(self):
        """11 strictly-falling closes: first 4 have no 4-bar lookback, the
        next 7 each close below the close 4 bars earlier -> running +7."""
        close = pd.Series([100 - i for i in range(11)])
        assert su.compute_td_setup(close).iloc[-1] == 7

    def test_completed_buy_setup_reports_nine(self):
        close = pd.Series([100 - i for i in range(13)])
        assert su.compute_td_setup(close).iloc[-1] == 9

    def test_completed_sell_setup_reports_negative_nine(self):
        close = pd.Series([100 + i for i in range(13)])
        assert su.compute_td_setup(close).iloc[-1] == -9

    def test_flip_resets_and_reverses_the_count(self):
        # falls for 3 buy-bars (+1,+2,+3) then rises for 3 sell-bars (-1,-2,-3)
        close = pd.Series([10, 10, 10, 10, 9, 8, 7, 11, 12, 13])
        assert list(su.compute_td_setup(close)) == [0, 0, 0, 0, 1, 2, 3, -1, -2, -3]

    def test_neutral_bar_resets_to_zero(self):
        # bar 6 closes equal to the close 4 bars earlier -> run resets to 0
        close = pd.Series([10, 10, 10, 10, 9, 8, 10, 9])
        assert list(su.compute_td_setup(close)) == [0, 0, 0, 0, 1, 2, 0, 1]

    def test_short_history_is_zero(self):
        close = pd.Series([5, 4, 3, 2])  # < 5 bars: no 4-bar lookback yet
        assert list(su.compute_td_setup(close)) == [0, 0, 0, 0]

    def test_magnitude_caps_at_nine(self):
        close = pd.Series([100 - i for i in range(15)])  # would be +11 uncapped
        out = su.compute_td_setup(close)
        assert out.iloc[-1] == 9
        assert out.max() == 9


@pytest.mark.unit
class TestTdSetupByTimeframe:
    def test_returns_all_three_signed_keys(self):
        counts = su.td_setup_by_timeframe(_ohlcv([100 - i for i in range(320)]))
        assert set(counts) == {"weekly", "monthly", "daily"}
        assert all(isinstance(v, int) for v in counts.values())

    def test_falling_series_is_a_buy_setup_on_every_timeframe(self):
        # 320 strictly-falling business days -> falling weekly & monthly closes too
        counts = su.td_setup_by_timeframe(_ohlcv([100 - i for i in range(320)]))
        assert counts == {"weekly": 9, "monthly": 9, "daily": 9}

    def test_rising_series_is_a_sell_setup_on_every_timeframe(self):
        counts = su.td_setup_by_timeframe(_ohlcv([100 + i for i in range(320)]))
        assert counts == {"weekly": -9, "monthly": -9, "daily": -9}

    def test_curr_date_excludes_future_bars(self):
        # A late rising tail must not leak in when curr_date predates it.
        df = _ohlcv([100 - i for i in range(20)] + [200 + i for i in range(20)])
        cutoff = df["Date"].iloc[19].strftime("%Y-%m-%d")
        counts = su.td_setup_by_timeframe(df, cutoff)
        assert counts["daily"] > 0  # still a buy-setup, future rise ignored


@pytest.mark.unit
class TestFormatTdSetupBlock:
    def test_lists_three_tiers_with_signed_counts(self):
        block = su.format_td_setup_block({"weekly": 7, "monthly": -3, "daily": 9})
        for token in ("Tier 1", "Tier 2", "Tier 3", "Weekly", "Monthly", "Daily"):
            assert token in block
        assert "+7" in block and "-3" in block and "+9" in block

    def test_completed_nine_is_flagged(self):
        block = su.format_td_setup_block({"weekly": 9, "monthly": 0, "daily": 0})
        assert "9 of 9" in block

    def test_zero_reads_as_no_active_setup(self):
        block = su.format_td_setup_block({"weekly": 0, "monthly": 0, "daily": 0})
        assert "no active setup" in block


@pytest.mark.unit
class TestYFinanceWindowWiring:
    def test_td_9_returns_tiered_block_without_valueerror(self, monkeypatch):
        """`td_9` is a legal indicator name in the yfinance window and emits the
        three-tier block — it must NOT raise the "not supported" ValueError that
        unknown names trigger."""
        from tradingagents.dataflows import y_finance

        frame = _ohlcv([100 - i for i in range(320)])
        monkeypatch.setattr(y_finance, "load_ohlcv", lambda symbol, curr_date: frame)

        out = y_finance.get_stock_stats_indicators_window(
            "AAPL", "td_9", "2026-06-04", 30
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
    def test_td_9_raises_so_router_falls_back_to_yfinance(self):
        """Alpha Vantage has no TD endpoint. `td_9` raises the standard
        "not supported" ValueError; route_to_vendor's catch-all then falls
        through to yfinance (which computes it from OHLCV). This is the repo's
        existing fallback contract — no placebo string that would short-circuit
        the chain on the first non-exception return."""
        from tradingagents.dataflows import alpha_vantage_indicator as av

        with pytest.raises(ValueError):
            av.get_indicator("AAPL", "td_9", "2026-06-04", 30)

    def test_route_to_vendor_falls_back_to_yfinance(self, monkeypatch):
        """End-to-end: with Alpha Vantage forced primary, a td_9 call still
        returns the real tiered block computed by yfinance."""
        import copy
        from tradingagents.dataflows import y_finance, interface
        from tradingagents.dataflows.config import get_config, set_config

        frame = _ohlcv([100 + i for i in range(320)])  # rising -> sell-setup
        monkeypatch.setattr(y_finance, "load_ohlcv", lambda symbol, curr_date: frame)

        saved = copy.deepcopy(get_config())  # restore so the global config doesn't leak
        try:
            cfg = get_config()
            cfg.setdefault("tool_vendors", {})["get_indicators"] = "alpha_vantage"
            set_config(cfg)

            out = interface.route_to_vendor("get_indicators", "AAPL", "td_9", "2026-06-04", 30)
            assert "Tier 1 Weekly" in out
            assert "-9" in out
        finally:
            set_config(saved)
