"""Tests for scanner data functions — yfinance fallback and AV error handling.

These tests verify:
1. yfinance sector performance returns real data via ETF proxies
2. yfinance industry performance uses DataFrame index for ticker symbols
3. AV scanner functions raise AlphaVantageError when all data fails (enabling fallback)
4. route_to_vendor falls back from AV to yfinance on AlphaVantageError
"""

import os
import pytest
from unittest.mock import patch

from tradingagents.dataflows.yfinance_scanner import (
    get_sector_performance_yfinance,
    get_industry_performance_yfinance,
)
from tradingagents.dataflows.alpha_vantage_common import AlphaVantageError
from tradingagents.dataflows.alpha_vantage_scanner import (
    get_sector_performance_alpha_vantage,
    get_industry_performance_alpha_vantage,
)


class TestYfinanceSectorPerformance:
    """Verify yfinance sector performance uses ETF proxies and returns real data."""

    def test_returns_all_11_sectors(self):
        result = get_sector_performance_yfinance()
        assert "| Sector |" in result
        # Check all 11 GICS sectors are present
        for sector in [
            "Technology", "Healthcare", "Financials", "Energy",
            "Consumer Discretionary", "Consumer Staples", "Industrials",
            "Materials", "Real Estate", "Utilities", "Communication Services",
        ]:
            assert sector in result, f"Missing sector: {sector}"

    def test_returns_numeric_percentages(self):
        result = get_sector_performance_yfinance()
        lines = result.strip().split("\n")
        # Skip header lines (first 4: title, date, column headers, separator)
        data_lines = [l for l in lines if l.startswith("| ") and "Sector" not in l and "---" not in l]
        assert len(data_lines) == 11, f"Expected 11 data rows, got {len(data_lines)}"

        for line in data_lines:
            cols = [c.strip() for c in line.split("|")[1:-1]]
            # cols: [sector_name, 1-day, 1-week, 1-month, ytd]
            assert len(cols) == 5, f"Expected 5 columns, got {len(cols)} in: {line}"
            # 1-day should be a percentage like "+1.45%" or "-0.31%"
            day_pct = cols[1]
            assert "%" in day_pct or day_pct == "N/A", f"Bad 1-day value: {day_pct}"
            # Should NOT contain "Error:"
            assert "Error:" not in day_pct, f"Error in 1-day for {cols[0]}: {day_pct}"


class TestYfinanceIndustryPerformance:
    """Verify yfinance industry performance uses index for ticker symbols."""

    def test_returns_real_symbols(self):
        result = get_industry_performance_yfinance("technology")
        assert "| Company |" in result or "| Company " in result
        # Should contain actual tickers, not N/A
        assert "NVDA" in result or "AAPL" in result or "MSFT" in result, \
            f"No real tickers found in result: {result[:300]}"

    def test_no_na_symbols(self):
        result = get_industry_performance_yfinance("technology")
        lines = result.strip().split("\n")
        data_lines = [l for l in lines if l.startswith("| ") and "Company" not in l and "---" not in l]
        for line in data_lines:
            cols = [c.strip() for c in line.split("|")[1:-1]]
            # Symbol column (index 1) should not be N/A
            assert cols[1] != "N/A", f"Symbol is N/A in line: {line}"

    def test_healthcare_sector(self):
        result = get_industry_performance_yfinance("healthcare")
        assert "Industry Performance: Healthcare" in result


class TestAlphaVantageFailoverRaise:
    """Verify AV scanner functions raise when all data fails (enabling fallback)."""

    def test_sector_perf_raises_on_total_failure(self):
        """When every GLOBAL_QUOTE call fails, the function should raise."""
        with patch.dict(os.environ, {"ALPHA_VANTAGE_API_KEY": "demo"}):
            with pytest.raises(AlphaVantageError, match="All .* sector queries failed"):
                get_sector_performance_alpha_vantage()

    def test_industry_perf_raises_on_total_failure(self):
        """When every ticker quote fails, the function should raise."""
        with patch.dict(os.environ, {"ALPHA_VANTAGE_API_KEY": "demo"}):
            with pytest.raises(AlphaVantageError, match="All .* ticker queries failed"):
                get_industry_performance_alpha_vantage("technology")


class TestRouteToVendorFallback:
    """Verify route_to_vendor falls back from AV to yfinance."""

    def test_sector_perf_falls_back_to_yfinance(self):
        with patch.dict(os.environ, {"ALPHA_VANTAGE_API_KEY": "demo"}):
            from tradingagents.dataflows.interface import route_to_vendor
            result = route_to_vendor("get_sector_performance")
            # Should get yfinance data (no "Alpha Vantage" in header)
            assert "Sector Performance Overview" in result
            # Should have actual percentage data, not all errors
            assert "Error:" not in result or result.count("Error:") < 3

    def test_industry_perf_falls_back_to_yfinance(self):
        with patch.dict(os.environ, {"ALPHA_VANTAGE_API_KEY": "demo"}):
            from tradingagents.dataflows.interface import route_to_vendor
            result = route_to_vendor("get_industry_performance", "technology")
            assert "Industry Performance" in result
            # Should contain real ticker symbols
            assert "N/A" not in result or result.count("N/A") < 5
