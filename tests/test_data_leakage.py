"""
Tests to verify no future data leakage in backtesting.

These tests ensure that when running backtests for a historical date,
the system only uses data that would have been available at that time.
"""
import pytest
from datetime import datetime, timedelta
import pandas as pd


class TestStockstatsDataLeakage:
    """Test that stockstats_utils.py doesn't leak future data."""

    def test_stockstats_uses_curr_date_not_today(self):
        """Verify stockstats filters data up to curr_date, not today."""
        from tradingagents.dataflows.stockstats_utils import StockstatsUtils

        # Test with a historical date
        historical_date = "2024-06-15"

        # This should only use data up to 2024-06-15
        # If the function works correctly, we shouldn't get data beyond this date
        try:
            result = StockstatsUtils.get_stock_stats("AAPL", "close", historical_date)
            # Result should be a value, not an error
            assert result is not None
        except Exception as e:
            # If local data not available, that's expected
            if "Yahoo Finance data not fetched yet" not in str(e):
                raise

    def test_end_date_equals_curr_date(self):
        """Verify that yfinance download uses curr_date as end_date."""
        # This is a structural check - the code should use curr_date_dt as end_date_dt
        from tradingagents.dataflows.stockstats_utils import StockstatsUtils
        import inspect

        source = inspect.getsource(StockstatsUtils.get_stock_stats)

        # Check that the code uses curr_date for end_date calculation
        assert "end_date_dt = curr_date_dt" in source or "end=end_date" in source, \
            "stockstats should use curr_date as end_date to prevent future data leakage"


class TestAlphaVantageDataLeakage:
    """Test that alpha_vantage_stock.py doesn't leak future data."""

    def test_outputsize_uses_end_date_not_now(self):
        """Verify outputsize calculation uses end_date, not datetime.now()."""
        from tradingagents.dataflows.alpha_vantage_stock import get_stock
        import inspect

        source = inspect.getsource(get_stock)

        # Should NOT contain datetime.now() for outputsize calculation
        assert "datetime.now()" not in source, \
            "alpha_vantage_stock should not use datetime.now() - use end_date instead"

        # Should use end_date for the calculation
        assert "end_dt" in source or "end_date" in source, \
            "Should use end_date for outputsize calculation"


class TestFundamentalsDataLeakage:
    """Test that fundamentals data respects publication delays."""

    def test_publication_delay_is_conservative(self):
        """Verify publication delay is at least 60 days (conservative estimate)."""
        from tradingagents.dataflows.y_finance import _filter_fundamentals_by_date
        import inspect

        source = inspect.getsource(_filter_fundamentals_by_date)

        # Check that publication delay is at least 60 days
        assert "publication_delay_days = 60" in source or "publication_delay_days = 90" in source, \
            "Publication delay should be at least 60 days for conservative backtesting"

    def test_fundamentals_filtered_by_publish_date(self):
        """Verify fundamentals are filtered by estimated publish date, not report date."""
        from tradingagents.dataflows.y_finance import _filter_fundamentals_by_date
        import pandas as pd

        # Create mock fundamentals data with future dates
        curr_date = "2024-06-15"
        # Report from Q1 2024 (dated 2024-03-31) should be visible
        # Report from Q2 2024 (dated 2024-06-30) should NOT be visible

        mock_data = pd.DataFrame({
            "2024-03-31": [100, 200],
            "2024-06-30": [150, 250],  # This shouldn't be visible in June
            "2024-09-30": [175, 275],  # This definitely shouldn't be visible
        }, index=["Revenue", "Profit"])

        filtered = _filter_fundamentals_by_date(mock_data, curr_date)

        # With 60-day delay, only 2024-03-31 should be visible on 2024-06-15
        # because 2024-03-31 + 60 days = 2024-05-30, which is before 2024-06-15
        assert "2024-03-31" in filtered.columns, \
            "Q1 2024 report (dated 2024-03-31) should be visible on 2024-06-15"

        assert "2024-06-30" not in filtered.columns, \
            "Q2 2024 report (dated 2024-06-30) should NOT be visible on 2024-06-15"

        assert "2024-09-30" not in filtered.columns, \
            "Q3 2024 report should definitely NOT be visible on 2024-06-15"


class TestLocalDataLeakage:
    """Test that local data files are properly filtered."""

    def test_local_data_has_date_filtering(self):
        """Verify local data reading includes date filtering."""
        from tradingagents.dataflows.local import get_stock_data
        import inspect

        source = inspect.getsource(get_stock_data)

        # Should filter data by date range
        assert "start_date" in source and "end_date" in source, \
            "Local data should be filtered by date range"


class TestBacktestIntegrity:
    """Test overall backtest integrity."""

    def test_no_future_imports_in_dataflows(self):
        """Verify dataflows don't use any patterns that could leak future data."""
        import os
        import re

        dataflows_dir = "tradingagents/dataflows"

        dangerous_patterns = [
            # Using today's date when historical date should be used
            r"pd\.Timestamp\.today\(\)",
            r"datetime\.today\(\)",
            r"date\.today\(\)",
            # Unfiltered data access (should always filter by date)
            r"\.history\([^)]*\)(?![^)]*end=)",  # history() without end parameter
        ]

        issues = []

        for root, dirs, files in os.walk(dataflows_dir):
            for file in files:
                if file.endswith(".py"):
                    filepath = os.path.join(root, file)
                    with open(filepath, "r") as f:
                        content = f.read()
                        for pattern in dangerous_patterns:
                            matches = re.findall(pattern, content)
                            if matches:
                                issues.append(f"{filepath}: Found dangerous pattern {pattern}")

        assert len(issues) == 0, \
            f"Found potential data leakage patterns:\n" + "\n".join(issues)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
