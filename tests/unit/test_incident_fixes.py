"""Unit tests for the incident-fix improvements across the dataflows layer.

Tests cover:
  1. _load_or_fetch_ohlcv — dynamic cache filename, corruption detection + re-fetch
  2. YFinanceError — propagated by get_stockstats_indicator (no more silent return "")
  3. _filter_csv_by_date_range — explicit date column discovery (no positional assumption)
"""

import os
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_ohlcv_df(periods: int = 200) -> pd.DataFrame:
    """Return a minimal valid OHLCV DataFrame with a Date column."""
    idx = pd.date_range("2024-01-02", periods=periods, freq="B")
    return pd.DataFrame(
        {
            "Date": idx.strftime("%Y-%m-%d"),
            "Open": [100.0] * periods,
            "High": [105.0] * periods,
            "Low": [95.0] * periods,
            "Close": [102.0] * periods,
            "Volume": [1_000_000] * periods,
        }
    )


# ---------------------------------------------------------------------------
# _load_or_fetch_ohlcv — cache + download logic
# ---------------------------------------------------------------------------

class TestLoadOrFetchOhlcv:
    """Tests for the unified OHLCV loader."""

    def test_downloads_and_caches_on_first_call(self, tmp_path):
        """When no cache exists, yfinance is called and data is written to cache."""
        from tradingagents.dataflows.stockstats_utils import _load_or_fetch_ohlcv

        expected_df = _minimal_ohlcv_df()
        mock_downloaded = expected_df.copy()
        mock_downloaded.index = pd.RangeIndex(len(mock_downloaded))  # simulate reset_index output

        with (
            patch("tradingagents.dataflows.stockstats_utils.get_config",
                  return_value={"data_cache_dir": str(tmp_path), "data_vendors": {"technical_indicators": "yfinance"}}),
            patch("tradingagents.dataflows.stockstats_utils.yf.download",
                  return_value=expected_df.set_index("Date")) as mock_dl,
        ):
            result = _load_or_fetch_ohlcv("AAPL")
            mock_dl.assert_called_once()

        # Cache file must exist after the call
        csv_files = list(tmp_path.glob("AAPL-YFin-data-*.csv"))
        assert len(csv_files) == 1, "Expected exactly one cache file to be created"

    def test_uses_cache_on_second_call(self, tmp_path):
        """When cache already exists, yfinance.download is NOT called again."""
        from tradingagents.dataflows.stockstats_utils import _load_or_fetch_ohlcv

        # Write a valid cache file manually
        df = _minimal_ohlcv_df()
        today = pd.Timestamp.today()
        start = (today - pd.DateOffset(years=15)).strftime("%Y-%m-%d")
        end = today.strftime("%Y-%m-%d")
        cache_file = tmp_path / f"AAPL-YFin-data-{start}-{end}.csv"
        df.to_csv(cache_file, index=False)

        with (
            patch("tradingagents.dataflows.stockstats_utils.get_config",
                  return_value={"data_cache_dir": str(tmp_path), "data_vendors": {"technical_indicators": "yfinance"}}),
            patch("tradingagents.dataflows.stockstats_utils.yf.download") as mock_dl,
        ):
            result = _load_or_fetch_ohlcv("AAPL")
            mock_dl.assert_not_called()

        assert len(result) == 200

    def test_corrupt_cache_is_deleted_and_refetched(self, tmp_path):
        """A corrupt (unparseable) cache file is deleted and yfinance is called again."""
        from tradingagents.dataflows.stockstats_utils import _load_or_fetch_ohlcv

        today = pd.Timestamp.today()
        start = (today - pd.DateOffset(years=15)).strftime("%Y-%m-%d")
        end = today.strftime("%Y-%m-%d")
        cache_file = tmp_path / f"AAPL-YFin-data-{start}-{end}.csv"
        cache_file.write_text(",,,,CORRUPT,,\x00\x00BINARY GARBAGE")

        fresh_df = _minimal_ohlcv_df()

        with (
            patch("tradingagents.dataflows.stockstats_utils.get_config",
                  return_value={"data_cache_dir": str(tmp_path), "data_vendors": {"technical_indicators": "yfinance"}}),
            patch("tradingagents.dataflows.stockstats_utils.yf.download",
                  return_value=fresh_df.set_index("Date")) as mock_dl,
        ):
            result = _load_or_fetch_ohlcv("AAPL")
            mock_dl.assert_called_once()

    def test_truncated_cache_triggers_refetch(self, tmp_path):
        """A cache file with fewer than 50 rows is treated as truncated and re-fetched."""
        from tradingagents.dataflows.stockstats_utils import _load_or_fetch_ohlcv

        tiny_df = _minimal_ohlcv_df(periods=10)  # only 10 rows — well below threshold
        today = pd.Timestamp.today()
        start = (today - pd.DateOffset(years=15)).strftime("%Y-%m-%d")
        end = today.strftime("%Y-%m-%d")
        cache_file = tmp_path / f"AAPL-YFin-data-{start}-{end}.csv"
        tiny_df.to_csv(cache_file, index=False)

        fresh_df = _minimal_ohlcv_df()

        with (
            patch("tradingagents.dataflows.stockstats_utils.get_config",
                  return_value={"data_cache_dir": str(tmp_path), "data_vendors": {"technical_indicators": "yfinance"}}),
            patch("tradingagents.dataflows.stockstats_utils.yf.download",
                  return_value=fresh_df.set_index("Date")) as mock_dl,
        ):
            result = _load_or_fetch_ohlcv("AAPL")
            mock_dl.assert_called_once()

    def test_empty_download_raises_yfinance_error(self, tmp_path):
        """An empty DataFrame from yfinance raises YFinanceError (not a silent return)."""
        from tradingagents.dataflows.stockstats_utils import _load_or_fetch_ohlcv, YFinanceError

        with (
            patch("tradingagents.dataflows.stockstats_utils.get_config",
                  return_value={"data_cache_dir": str(tmp_path), "data_vendors": {"technical_indicators": "yfinance"}}),
            patch("tradingagents.dataflows.stockstats_utils.yf.download",
                  return_value=pd.DataFrame()),
        ):
            with pytest.raises(YFinanceError, match="no data"):
                _load_or_fetch_ohlcv("INVALID_TICKER_XYZ")

    def test_cache_filename_is_dynamic_not_hardcoded(self, tmp_path):
        """Cache filename contains today's date (not a hardcoded historical date like 2025-03-25)."""
        from tradingagents.dataflows.stockstats_utils import _load_or_fetch_ohlcv

        df = _minimal_ohlcv_df()

        with (
            patch("tradingagents.dataflows.stockstats_utils.get_config",
                  return_value={"data_cache_dir": str(tmp_path), "data_vendors": {"technical_indicators": "yfinance"}}),
            patch("tradingagents.dataflows.stockstats_utils.yf.download",
                  return_value=df.set_index("Date")),
        ):
            _load_or_fetch_ohlcv("AAPL")

        csv_files = list(tmp_path.glob("AAPL-YFin-data-*.csv"))
        assert len(csv_files) == 1
        filename = csv_files[0].name
        # Must NOT contain the old hardcoded stale date
        assert "2025-03-25" not in filename, (
            f"Cache filename contains the old hardcoded stale date! Got: {filename}"
        )
        # Must contain today's year
        today_year = str(pd.Timestamp.today().year)
        assert today_year in filename, f"Expected today's year {today_year} in filename: {filename}"


# ---------------------------------------------------------------------------
# YFinanceError propagation (no more silent return "")
# ---------------------------------------------------------------------------

class TestYFinanceErrorPropagation:
    """Tests that YFinanceError is raised (not swallowed) by get_stockstats_indicator."""

    def test_get_stockstats_indicator_raises_yfinance_error_on_failure(self, tmp_path):
        """get_stockstats_indicator raises YFinanceError when yfinance returns empty data."""
        from tradingagents.dataflows.stockstats_utils import YFinanceError
        from tradingagents.dataflows.y_finance import get_stockstats_indicator

        with (
            patch("tradingagents.dataflows.stockstats_utils.get_config",
                  return_value={"data_cache_dir": str(tmp_path), "data_vendors": {"technical_indicators": "yfinance"}}),
            patch("tradingagents.dataflows.stockstats_utils.yf.download",
                  return_value=pd.DataFrame()),
        ):
            with pytest.raises(YFinanceError):
                get_stockstats_indicator("INVALID", "rsi", "2025-01-02")

    def test_yfinance_error_is_not_swallowed_as_empty_string(self, tmp_path):
        """Regression test: get_stockstats_indicator must NOT return empty string on error."""
        from tradingagents.dataflows.stockstats_utils import YFinanceError
        from tradingagents.dataflows.y_finance import get_stockstats_indicator

        with (
            patch("tradingagents.dataflows.stockstats_utils.get_config",
                  return_value={"data_cache_dir": str(tmp_path), "data_vendors": {"technical_indicators": "yfinance"}}),
            patch("tradingagents.dataflows.stockstats_utils.yf.download",
                  return_value=pd.DataFrame()),
        ):
            result = None
            try:
                result = get_stockstats_indicator("INVALID", "rsi", "2025-01-02")
            except YFinanceError:
                pass  # This is the correct behaviour

            assert result is None, (
                "get_stockstats_indicator should raise YFinanceError, not silently return a value. "
                f"Got: {result!r}"
            )


# ---------------------------------------------------------------------------
# _filter_csv_by_date_range — explicit column discovery
# ---------------------------------------------------------------------------

class TestFilterCsvByDateRange:
    """Tests for the fixed _filter_csv_by_date_range in alpha_vantage_common."""

    def _make_av_csv(self, date_col_name: str = "time") -> str:
        return (
            f"{date_col_name},SMA\n"
            "2024-01-02,230.5\n"
            "2024-01-03,231.0\n"
            "2024-01-08,235.5\n"
        )

    def test_filters_with_standard_time_column(self):
        """Standard Alpha Vantage CSV with 'time' header filters correctly."""
        from tradingagents.dataflows.alpha_vantage_common import _filter_csv_by_date_range

        result = _filter_csv_by_date_range(self._make_av_csv("time"), "2024-01-03", "2024-01-08")
        assert "2024-01-02" not in result
        assert "2024-01-03" in result
        assert "2024-01-08" in result

    def test_filters_with_timestamp_column(self):
        """CSV with 'timestamp' header (alternative AV format) also works."""
        from tradingagents.dataflows.alpha_vantage_common import _filter_csv_by_date_range

        result = _filter_csv_by_date_range(self._make_av_csv("timestamp"), "2024-01-03", "2024-01-08")
        assert "2024-01-02" not in result
        assert "2024-01-03" in result

    def test_missing_date_column_raises_not_silently_filters_wrong_column(self):
        """When no recognised date column exists, raises ValueError immediately.
        Previously it would silently use df.columns[0] and return garbage."""
        from tradingagents.dataflows.alpha_vantage_common import _filter_csv_by_date_range

        bad_csv = "price,volume\n102.0,1000\n103.0,2000\n"

        # The fixed code raises ValueError; the old code would silently try to
        # parse the 'price' column as a date and return the original data.
        with pytest.raises(ValueError, match="Date column not found"):
            _filter_csv_by_date_range(bad_csv, "2024-01-01", "2024-01-31")

    def test_empty_csv_returns_empty(self):
        """Empty input returns empty output without error."""
        from tradingagents.dataflows.alpha_vantage_common import _filter_csv_by_date_range

        result = _filter_csv_by_date_range("", "2024-01-01", "2024-01-31")
        assert result == ""
