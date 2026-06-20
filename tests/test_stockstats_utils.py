"""Tests for stockstats_utils functionality.

Merged from:
- test_stockstats_date_column.py — date column handling (#890)
- test_stockstats_utils.py — core utils, retry, cleaning, filtering
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from yfinance.exceptions import YFRateLimitError

from tradingagents.dataflows.stockstats_utils import (
    StockstatsUtils,
    _clean_dataframe,
    _ensure_date_column,
    filter_financials_by_date,
    load_ohlcv,
    yf_retry,
)
from tradingagents.dataflows import stockstats_utils as su


class _TempDirMixin:
    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(str(self._tmp), ignore_errors=True)


def _ohlcv(date_col: str) -> pd.DataFrame:
    """OHLCV frame whose date column is named `date_col`."""
    dates = pd.bdate_range("2026-04-01", periods=10)
    return pd.DataFrame({
        date_col: dates,
        "Open": [100.0 + i for i in range(10)],
        "High": [101.0 + i for i in range(10)],
        "Low": [99.0 + i for i in range(10)],
        "Close": [100.5 + i for i in range(10)],
        "Volume": [1_000_000 + i for i in range(10)],
    })


@pytest.mark.unit
class YfRetryTests(unittest.TestCase):
    def test_succeeds_on_first_attempt(self):
        func = MagicMock(return_value=42)
        self.assertEqual(yf_retry(func), 42)
        func.assert_called_once()

    def test_retries_on_rate_limit(self):
        func = MagicMock(
            side_effect=[YFRateLimitError(), YFRateLimitError(), 42]
        )
        self.assertEqual(yf_retry(func, max_retries=3), 42)
        self.assertEqual(func.call_count, 3)

    def test_raises_after_exhausting_retries(self):
        func = MagicMock(side_effect=YFRateLimitError())
        with self.assertRaises(YFRateLimitError):
            yf_retry(func, max_retries=2)
        self.assertEqual(func.call_count, 3)

    def test_passes_args_through(self):
        func = MagicMock(return_value="ok")
        result = yf_retry(lambda: func("arg1", key="val"))
        self.assertEqual(result, "ok")
        func.assert_called_once_with("arg1", key="val")


@pytest.mark.unit
class EnsureDateColumnTests(unittest.TestCase):
    def test_preserves_existing_date_column(self):
        df = pd.DataFrame({"Date": ["2026-01-01"], "Close": [100.0]})
        result = _ensure_date_column(df)
        self.assertIn("Date", result.columns)

    def test_renames_index_column(self):
        df = pd.DataFrame({"Close": [100.0]})
        df.index.name = "index"
        result = _ensure_date_column(df.reset_index())
        self.assertIn("Date", result.columns)

    def test_renames_datetime_column(self):
        df = pd.DataFrame({"Datetime": ["2026-01-01"], "Close": [100.0]})
        result = _ensure_date_column(df)
        self.assertIn("Date", result.columns)

    def test_returns_unchanged_when_no_candidate(self):
        df = pd.DataFrame({"Close": [100.0]})
        result = _ensure_date_column(df)
        self.assertNotIn("Date", result.columns)


@pytest.mark.unit
class CleanDataframeTests(unittest.TestCase):
    def setUp(self):
        self.raw = pd.DataFrame({
            "Date": ["2026-01-02", "2026-01-03"],
            "Open": [100.0, 101.0],
            "High": [105.0, 106.0],
            "Low": [99.0, 100.0],
            "Close": [102.0, 103.0],
            "Volume": [10000, 12000],
        })

    def test_cleans_dataframe(self):
        result = _clean_dataframe(self.raw)
        self.assertIn("Date", result.columns)
        self.assertEqual(len(result), 2)

    def test_drops_rows_with_no_close(self):
        df = self.raw.copy()
        df.loc[1, "Close"] = None
        result = _clean_dataframe(df)
        self.assertEqual(len(result), 1)

    def test_fills_price_gaps(self):
        df = self.raw.copy()
        df.loc[0, "Close"] = None
        result = _clean_dataframe(df)
        self.assertEqual(result["Close"].iloc[0], 103.0)


@pytest.mark.unit
class FilterFinancialsByDateTests(unittest.TestCase):
    def test_filters_future_columns(self):
        df = pd.DataFrame({"2026-01-01": [100], "2027-01-01": [200]})
        result = filter_financials_by_date(df, "2026-06-01")
        self.assertIn("2026-01-01", result.columns)
        self.assertNotIn("2027-01-01", result.columns)

    def test_returns_empty_dataframe_unchanged(self):
        df = pd.DataFrame()
        result = filter_financials_by_date(df, "2026-06-01")
        self.assertTrue(result.empty)

    def test_returns_data_when_no_curr_date(self):
        df = pd.DataFrame({"col": [1]})
        result = filter_financials_by_date(df, "")
        self.assertIn("col", result.columns)


@pytest.mark.unit
class TestEnsureDateColumn:
    def test_renames_index_column(self):
        out = su._ensure_date_column(_ohlcv("index"))
        assert "Date" in out.columns and "index" not in out.columns

    def test_renames_datetime_and_date_variants(self):
        assert "Date" in su._ensure_date_column(_ohlcv("Datetime")).columns
        assert "Date" in su._ensure_date_column(_ohlcv("date")).columns

    def test_leaves_existing_date_untouched(self):
        df = _ohlcv("Date")
        assert su._ensure_date_column(df) is df  # no-op short-circuit

    def test_no_datelike_column_is_left_alone(self):
        df = pd.DataFrame({"Close": [1, 2, 3]})
        out = su._ensure_date_column(df)
        assert "Date" not in out.columns  # nothing to rename; caller handles


@pytest.mark.unit
class TestCleanDataframeAcrossVersions:
    def test_clean_handles_index_column(self):
        """A frame with `index` instead of `Date` must still clean to a
        usable, date-parsed frame (was KeyError: 'Date')."""
        cleaned = su._clean_dataframe(_ohlcv("index"))
        assert "Date" in cleaned.columns
        assert pd.api.types.is_datetime64_any_dtype(cleaned["Date"])
        assert len(cleaned) == 10

    def test_clean_handles_legacy_date_column(self):
        cleaned = su._clean_dataframe(_ohlcv("Date"))
        assert len(cleaned) == 10

    def test_indicators_compute_after_index_rename(self):
        """stockstats must compute indicators on a frame whose date column
        arrived as `index`, instead of erroring per indicator."""
        from stockstats import wrap
        cleaned = su._clean_dataframe(_ohlcv("index"))
        df = wrap(cleaned)
        df["close_5_sma"]  # triggers calculation
        assert "close_5_sma" in df.columns
        assert df["close_5_sma"].notna().any()


# =========================================================================
# Edge-case tests merged from test_remaining_coverage.py
# =========================================================================


@pytest.mark.unit
class LoadOhlcvCacheTests(_TempDirMixin, unittest.TestCase):
    """Lines 100-102: cache hit from CSV."""

    def _cache_path(self):
        safe = "AAPL"
        today = pd.Timestamp.today()
        start = (today - pd.DateOffset(years=5)).strftime("%Y-%m-%d")
        end = today.strftime("%Y-%m-%d")
        return self._tmp / f"{safe}-YFin-data-{start}-{end}.csv"

    def test_uses_cached_csv(self):
        cache_dir = self._tmp
        data_file = self._cache_path()
        cached_df = pd.DataFrame({
            "Date": ["2026-01-02", "2026-01-03"],
            "Open": [99.0, 100.0],
            "High": [102.0, 103.0],
            "Low": [98.0, 99.0],
            "Close": [100.0, 101.0],
            "Volume": [10000, 11000],
        })
        cached_df.to_csv(data_file, index=False, encoding="utf-8")

        with patch("tradingagents.dataflows.stockstats_utils.get_config",
                   return_value={"data_cache_dir": str(cache_dir)}):
            result = load_ohlcv("AAPL", "2026-01-03", lookback_years=5)

        self.assertIsNotNone(result)
        self.assertEqual(len(result), 2)

    def test_empty_cached_file_is_miss(self):
        cache_dir = self._tmp
        data_file = self._cache_path()
        pd.DataFrame(columns=["Date", "Close"]).to_csv(data_file, index=False, encoding="utf-8")

        downloaded = pd.DataFrame({
            "Date": ["2026-01-02", "2026-01-03"],
            "Close": [100.0, 101.0],
            "Open": [99.0, 100.0],
            "High": [102.0, 103.0],
            "Low": [98.0, 99.0],
            "Volume": [10000, 11000],
        })

        with patch("tradingagents.dataflows.stockstats_utils.get_config",
                   return_value={"data_cache_dir": str(cache_dir)}), \
             patch("tradingagents.dataflows.stockstats_utils.yf_retry",
                   return_value=downloaded):
            result = load_ohlcv("AAPL", "2026-01-03", lookback_years=5)

        self.assertIsNotNone(result)
        self.assertEqual(len(result), 2)


@pytest.mark.unit
class LoadOhlcvDownloadAndFilterTests(_TempDirMixin, unittest.TestCase):
    """Lines 119-127: download -> clean -> filter by curr_date."""

    def test_download_and_filter_by_curr_date(self):
        cache_dir = self._tmp

        downloaded = pd.DataFrame({
            "Date": ["2026-01-02", "2026-01-03", "2026-01-04"],
            "Open": [99.0, 100.0, 101.0],
            "High": [102.0, 103.0, 104.0],
            "Low": [98.0, 99.0, 100.0],
            "Close": [100.0, 101.0, 102.0],
            "Volume": [10000, 11000, 12000],
        })

        with patch("tradingagents.dataflows.stockstats_utils.get_config",
                   return_value={"data_cache_dir": str(cache_dir)}), \
             patch("tradingagents.dataflows.stockstats_utils.yf_retry",
                   return_value=downloaded):
            result = load_ohlcv("AAPL", "2026-01-03", lookback_years=5)

        self.assertEqual(len(result), 2)
        dates = result["Date"].values
        self.assertIn(pd.Timestamp("2026-01-02"), dates)
        self.assertIn(pd.Timestamp("2026-01-03"), dates)
        self.assertNotIn(pd.Timestamp("2026-01-04"), dates)


@pytest.mark.unit
class StockstatsUtilsGetStatsTests(unittest.TestCase):
    """Lines 116, 155-167: StockstatsUtils.get_stock_stats full flow."""

    @patch("tradingagents.dataflows.stockstats_utils.wrap")
    @patch("tradingagents.dataflows.stockstats_utils.load_ohlcv")
    def test_returns_indicator_value(self, mock_load, mock_wrap):
        mock_load.return_value = pd.DataFrame({
            "Date": pd.to_datetime(["2026-01-02", "2026-01-03"]),
            "Close": [100.0, 101.0],
        })
        mock_wrapped = pd.DataFrame({
            "Date": pd.to_datetime(["2026-01-02", "2026-01-03"]),
            "Close": [100.0, 101.0],
            "sma_20": [102.5, 103.0],
        })
        mock_wrap.return_value = mock_wrapped
        result = StockstatsUtils.get_stock_stats("AAPL", "sma_20", "2026-01-03")
        self.assertEqual(result, 103.0)

    @patch("tradingagents.dataflows.stockstats_utils.wrap")
    @patch("tradingagents.dataflows.stockstats_utils.load_ohlcv")
    def test_returns_na_for_non_trading_day(self, mock_load, mock_wrap):
        mock_load.return_value = pd.DataFrame({
            "Date": pd.to_datetime(["2026-01-02"]),
            "Close": [100.0],
        })
        mock_wrapped = pd.DataFrame({
            "Date": pd.to_datetime(["2026-01-02"]),
            "Close": [100.0],
            "sma_20": [102.0],
        })
        mock_wrap.return_value = mock_wrapped
        result = StockstatsUtils.get_stock_stats("AAPL", "sma_20", "2026-01-05")
        self.assertEqual(result, "N/A: Not a trading day (weekend or holiday)")


@pytest.mark.unit
class LoadOhlcvNoMarketDataTests(_TempDirMixin, unittest.TestCase):
    """Line 116: NoMarketDataError when download returns empty."""

    def test_raises_on_empty_download(self):
        cache_dir = self._tmp
        with patch("tradingagents.dataflows.stockstats_utils.get_config",
                   return_value={"data_cache_dir": str(cache_dir)}), \
             patch("tradingagents.dataflows.stockstats_utils.yf_retry",
                   return_value=pd.DataFrame()):
            from tradingagents.dataflows.symbol_utils import NoMarketDataError
            with self.assertRaises(NoMarketDataError):
                load_ohlcv("INVALID", "2026-01-03", lookback_years=5)


if __name__ == "__main__":
    unittest.main()
