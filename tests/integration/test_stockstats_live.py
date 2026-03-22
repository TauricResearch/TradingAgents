"""Live-data integration tests for the stockstats utilities.

These tests call the real yfinance API and therefore require network access.
They are marked with ``integration`` and are excluded from the default test
run (which uses ``--ignore=tests/integration``).

Run them explicitly with:

    python -m pytest tests/integration/test_stockstats_live.py -v --override-ini="addopts="

The tests validate the fix for the "Invalid number of return arguments after
parsing column name: 'Date'" error that occurred because stockstats.wrap()
promotes the lowercase ``date`` column to the DataFrame index, so the old
``df["Date"]`` access caused stockstats to try to parse "Date" as an indicator
name. The fix uses ``df.index.strftime("%Y-%m-%d")`` instead.
"""

import pytest
import pandas as pd


pytestmark = pytest.mark.integration

# A well-known trading day we can use for assertions
_TEST_DATE = "2025-01-02"
_TEST_TICKER = "AAPL"


# ---------------------------------------------------------------------------
# StockstatsUtils.get_stock_stats
# ---------------------------------------------------------------------------

class TestStockstatsUtilsLive:
    """Live tests for StockstatsUtils.get_stock_stats against real yfinance data."""

    def test_close_50_sma_returns_numeric(self):
        """close_50_sma indicator returns a numeric value for a known trading day."""
        from tradingagents.dataflows.stockstats_utils import StockstatsUtils

        result = StockstatsUtils.get_stock_stats(_TEST_TICKER, "close_50_sma", _TEST_DATE)

        assert result != "N/A: Not a trading day (weekend or holiday)", (
            f"Expected a numeric value for {_TEST_DATE}, got N/A (check if it's a holiday)"
        )
        # Should be a finite float-like value
        assert float(result) > 0, f"close_50_sma should be positive, got: {result}"

    def test_rsi_returns_value_in_valid_range(self):
        """RSI indicator returns a value in [0, 100] for a known trading day."""
        from tradingagents.dataflows.stockstats_utils import StockstatsUtils

        result = StockstatsUtils.get_stock_stats(_TEST_TICKER, "rsi", _TEST_DATE)

        assert result != "N/A: Not a trading day (weekend or holiday)", (
            f"Expected numeric RSI for {_TEST_DATE}"
        )
        rsi = float(result)
        assert 0.0 <= rsi <= 100.0, f"RSI must be in [0, 100], got: {rsi}"

    def test_macd_returns_numeric(self):
        """MACD indicator returns a numeric value for a known trading day."""
        from tradingagents.dataflows.stockstats_utils import StockstatsUtils

        result = StockstatsUtils.get_stock_stats(_TEST_TICKER, "macd", _TEST_DATE)

        assert result != "N/A: Not a trading day (weekend or holiday)"
        # MACD can be positive or negative — just confirm it's a valid float
        float(result)  # raises ValueError if not numeric

    def test_weekend_returns_na(self):
        """A weekend date returns the N/A holiday/weekend message."""
        from tradingagents.dataflows.stockstats_utils import StockstatsUtils

        # 2025-01-04 is a Saturday
        result = StockstatsUtils.get_stock_stats(_TEST_TICKER, "close_50_sma", "2025-01-04")

        assert result == "N/A: Not a trading day (weekend or holiday)", (
            f"Expected N/A for Saturday 2025-01-04, got: {result}"
        )

    def test_no_date_column_error(self):
        """Calling get_stock_stats must NOT raise the 'Date' column parsing error."""
        from tradingagents.dataflows.stockstats_utils import StockstatsUtils

        # This previously raised: Invalid number of return arguments after
        # parsing column name: 'Date'
        try:
            StockstatsUtils.get_stock_stats(_TEST_TICKER, "close_50_sma", _TEST_DATE)
        except Exception as e:
            if "Invalid number of return arguments" in str(e) and "Date" in str(e):
                pytest.fail(
                    "Regression: stockstats is still trying to parse 'Date' as an "
                    f"indicator. Error: {e}"
                )
            raise  # re-raise unexpected errors


# ---------------------------------------------------------------------------
# _get_stock_stats_bulk
# ---------------------------------------------------------------------------

class TestGetStockStatsBulkLive:
    """Live tests for _get_stock_stats_bulk against real yfinance data."""

    def test_returns_dict_with_date_keys(self):
        """Bulk method returns a non-empty dict with YYYY-MM-DD string keys."""
        from tradingagents.dataflows.y_finance import _get_stock_stats_bulk

        result = _get_stock_stats_bulk(_TEST_TICKER, "rsi", _TEST_DATE)

        assert isinstance(result, dict), "Expected dict from _get_stock_stats_bulk"
        assert len(result) > 0, "Expected non-empty result dict"

        # Keys should all be YYYY-MM-DD strings
        for key in list(result.keys())[:5]:
            pd.Timestamp(key)  # raises if not parseable

    def test_trading_day_has_numeric_value(self):
        """A known trading day has a numeric (non-N/A) value in the bulk result."""
        from tradingagents.dataflows.y_finance import _get_stock_stats_bulk

        result = _get_stock_stats_bulk(_TEST_TICKER, "rsi", _TEST_DATE)

        assert _TEST_DATE in result, (
            f"Expected {_TEST_DATE} in bulk result dict. Keys sample: {list(result.keys())[:5]}"
        )
        value = result[_TEST_DATE]
        assert value != "N/A", (
            f"Expected numeric RSI for {_TEST_DATE}, got N/A (check if it's a holiday)"
        )
        float(value)  # should be convertible to float

    def test_no_date_column_parsing_error(self):
        """Bulk method must not raise the 'Date' column parsing error (regression guard)."""
        from tradingagents.dataflows.y_finance import _get_stock_stats_bulk

        try:
            _get_stock_stats_bulk(_TEST_TICKER, "close_50_sma", _TEST_DATE)
        except Exception as e:
            if "Invalid number of return arguments" in str(e) and "Date" in str(e):
                pytest.fail(
                    "Regression: _get_stock_stats_bulk still hits the 'Date' indicator "
                    f"parsing error. Error: {e}"
                )
            raise

    def test_multiple_indicators_all_work(self):
        """All supported indicators can be computed without error."""
        from tradingagents.dataflows.y_finance import _get_stock_stats_bulk

        indicators = [
            "close_50_sma",
            "close_200_sma",
            "close_10_ema",
            "macd",
            "macds",
            "macdh",
            "rsi",
            "boll",
            "boll_ub",
            "boll_lb",
            "atr",
        ]

        for indicator in indicators:
            try:
                result = _get_stock_stats_bulk(_TEST_TICKER, indicator, _TEST_DATE)
                assert isinstance(result, dict), f"{indicator}: expected dict"
                assert len(result) > 0, f"{indicator}: expected non-empty dict"
            except Exception as e:
                pytest.fail(f"Indicator '{indicator}' raised an unexpected error: {e}")


# ---------------------------------------------------------------------------
# get_stock_stats_indicators_window (end-to-end with live data)
# ---------------------------------------------------------------------------

class TestGetStockStatsIndicatorsWindowLive:
    """Live end-to-end tests for get_stock_stats_indicators_window."""

    def test_rsi_window_returns_formatted_string(self):
        """Window function returns a multi-line string with RSI values over a date range."""
        from tradingagents.dataflows.y_finance import get_stock_stats_indicators_window

        result = get_stock_stats_indicators_window(_TEST_TICKER, "rsi", _TEST_DATE, look_back_days=5)

        assert isinstance(result, str)
        assert "rsi" in result.lower()
        assert _TEST_DATE in result
        # Should have date: value lines
        lines = [l for l in result.split("\n") if ":" in l and "-" in l]
        assert len(lines) > 0, "Expected date:value lines in result"

    def test_close_50_sma_window_contains_numeric_values(self):
        """50-day SMA window result contains actual numeric price values."""
        from tradingagents.dataflows.y_finance import get_stock_stats_indicators_window

        result = get_stock_stats_indicators_window(
            _TEST_TICKER, "close_50_sma", _TEST_DATE, look_back_days=10
        )

        assert isinstance(result, str)
        # At least some lines should have numeric values (not all N/A)
        value_lines = [l for l in result.split("\n") if ":" in l and l.strip().startswith("20")]
        numeric_values = []
        for line in value_lines:
            try:
                val = line.split(":", 1)[1].strip()
                numeric_values.append(float(val))
            except (ValueError, IndexError):
                pass  # N/A lines are expected for weekends

        assert len(numeric_values) > 0, (
            "Expected at least some numeric 50-SMA values in the 10-day window"
        )
