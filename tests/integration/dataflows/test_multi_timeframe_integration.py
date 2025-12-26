"""
Test suite for Multi-Timeframe Aggregation Integration Tests.

This module tests:
1. Integration with yfinance data format
2. Timezone handling in datetime indices
3. Volume preservation across aggregations
4. Real-world edge cases (gaps in data, single day, etc.)
5. End-to-end workflows (daily -> weekly -> monthly)

Test Coverage:
- Integration tests with yfinance-like data formats
- Timezone-aware datetime handling
- Data gaps and missing days (weekends, holidays)
- Volume accuracy across transformations
- Multiple aggregation chaining
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

pytestmark = pytest.mark.integration


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def yfinance_format_data():
    """
    Create data in yfinance format with timezone-aware DatetimeIndex.

    yfinance returns data with:
    - Timezone-aware datetime index (usually UTC or exchange timezone)
    - Capitalized column names (Open, High, Low, Close, Volume)
    - Business day frequency (no weekends)
    - Potential gaps for holidays
    """
    # Create 30 business days (excludes weekends)
    dates = pd.bdate_range('2024-01-01', periods=30, freq='B', tz='America/New_York')

    data = pd.DataFrame({
        'Open': [100.0 + i * 0.5 for i in range(30)],
        'High': [102.0 + i * 0.5 for i in range(30)],
        'Low': [99.0 + i * 0.5 for i in range(30)],
        'Close': [101.0 + i * 0.5 for i in range(30)],
        'Volume': [1000000 + i * 10000 for i in range(30)],
    }, index=dates)

    return data


@pytest.fixture
def data_with_gaps():
    """
    Create data with gaps (missing days for weekends and holidays).

    Simulates real market data where weekends and holidays are missing.
    """
    # Create dates but skip weekends and one holiday (Jan 15)
    all_dates = pd.date_range('2024-01-01', '2024-01-31', freq='D')

    # Filter to business days and remove Jan 15 (MLK Day)
    business_dates = [d for d in all_dates if d.weekday() < 5 and d.day != 15]

    data = pd.DataFrame({
        'Open': [100.0 + i * 0.5 for i in range(len(business_dates))],
        'High': [102.0 + i * 0.5 for i in range(len(business_dates))],
        'Low': [99.0 + i * 0.5 for i in range(len(business_dates))],
        'Close': [101.0 + i * 0.5 for i in range(len(business_dates))],
        'Volume': [1000000 + i * 10000 for i in range(len(business_dates))],
    }, index=pd.DatetimeIndex(business_dates))

    return data


@pytest.fixture
def timezone_aware_data():
    """Create data with different timezone configurations."""
    dates_utc = pd.date_range('2024-01-01', periods=30, freq='D', tz='UTC')
    dates_est = pd.date_range('2024-01-01', periods=30, freq='D', tz='America/New_York')
    dates_jst = pd.date_range('2024-01-01', periods=30, freq='D', tz='Asia/Tokyo')

    base_data = {
        'Open': [100.0 + i * 0.5 for i in range(30)],
        'High': [102.0 + i * 0.5 for i in range(30)],
        'Low': [99.0 + i * 0.5 for i in range(30)],
        'Close': [101.0 + i * 0.5 for i in range(30)],
        'Volume': [1000000 + i * 10000 for i in range(30)],
    }

    return {
        'utc': pd.DataFrame(base_data, index=dates_utc),
        'est': pd.DataFrame(base_data, index=dates_est),
        'jst': pd.DataFrame(base_data, index=dates_jst),
    }


# ============================================================================
# Test YFinance Integration
# ============================================================================

class TestYFinanceIntegration:
    """Test aggregation with yfinance-like data formats."""

    def test_aggregation_with_yfinance_format(self, yfinance_format_data):
        """Should handle yfinance format data correctly."""
        from tradingagents.dataflows.multi_timeframe import aggregate_to_weekly

        result = aggregate_to_weekly(yfinance_format_data, anchor='SUN')

        assert isinstance(result, pd.DataFrame)
        assert len(result) > 0

        # Should preserve timezone awareness
        assert result.index.tz is not None
        assert str(result.index.tz) == 'America/New_York'

        # Should have correct OHLCV columns
        assert all(col in result.columns for col in ['Open', 'High', 'Low', 'Close', 'Volume'])

        # Verify aggregation logic
        assert result.iloc[0]['Open'] == yfinance_format_data.iloc[0]['Open']
        assert result.iloc[-1]['Close'] == yfinance_format_data.iloc[-1]['Close']

    def test_timezone_handling(self, timezone_aware_data):
        """Should preserve timezone information across aggregations."""
        from tradingagents.dataflows.multi_timeframe import aggregate_to_weekly, aggregate_to_monthly

        for tz_name, data in timezone_aware_data.items():
            # Test weekly aggregation
            weekly = aggregate_to_weekly(data, anchor='SUN')
            assert isinstance(weekly, pd.DataFrame)
            assert weekly.index.tz is not None

            # Test monthly aggregation
            monthly = aggregate_to_monthly(data, period_end=True)
            assert isinstance(monthly, pd.DataFrame)
            assert monthly.index.tz is not None

    def test_volume_preservation(self, yfinance_format_data):
        """Total volume should be preserved across aggregations."""
        from tradingagents.dataflows.multi_timeframe import aggregate_to_weekly, aggregate_to_monthly

        original_total_volume = yfinance_format_data['Volume'].sum()

        # Test weekly aggregation preserves volume
        weekly = aggregate_to_weekly(yfinance_format_data, anchor='SUN')
        assert isinstance(weekly, pd.DataFrame)
        weekly_total_volume = weekly['Volume'].sum()
        assert weekly_total_volume == original_total_volume

        # Test monthly aggregation preserves volume
        monthly = aggregate_to_monthly(yfinance_format_data, period_end=True)
        assert isinstance(monthly, pd.DataFrame)
        monthly_total_volume = monthly['Volume'].sum()
        assert monthly_total_volume == original_total_volume

    def test_business_day_frequency_handling(self):
        """Should handle business day frequency (no weekends) correctly."""
        from tradingagents.dataflows.multi_timeframe import aggregate_to_weekly

        # Create 20 business days (4 weeks excluding weekends)
        dates = pd.bdate_range('2024-01-01', periods=20, freq='B')
        data = pd.DataFrame({
            'Open': range(100, 120),
            'High': range(102, 122),
            'Low': range(99, 119),
            'Close': range(101, 121),
            'Volume': range(1000000, 1020000, 1000),
        }, index=dates)

        result = aggregate_to_weekly(data, anchor='SUN')

        assert isinstance(result, pd.DataFrame)
        # Should create appropriate number of weeks
        assert len(result) >= 4

        # Verify volume preservation
        assert result['Volume'].sum() == data['Volume'].sum()


# ============================================================================
# Test Edge Cases
# ============================================================================

class TestEdgeCases:
    """Test edge cases and real-world scenarios."""

    def test_single_day_data(self):
        """Should handle single day of data correctly."""
        from tradingagents.dataflows.multi_timeframe import aggregate_to_weekly, aggregate_to_monthly

        dates = pd.date_range('2024-01-15', periods=1, freq='D')
        data = pd.DataFrame({
            'Open': [100.0],
            'High': [102.0],
            'Low': [99.0],
            'Close': [101.0],
            'Volume': [1000000],
        }, index=dates)

        # Weekly aggregation
        weekly = aggregate_to_weekly(data, anchor='SUN')
        assert isinstance(weekly, pd.DataFrame)
        assert len(weekly) == 1
        assert weekly.iloc[0]['Open'] == 100.0
        assert weekly.iloc[0]['High'] == 102.0
        assert weekly.iloc[0]['Low'] == 99.0
        assert weekly.iloc[0]['Close'] == 101.0
        assert weekly.iloc[0]['Volume'] == 1000000

        # Monthly aggregation
        monthly = aggregate_to_monthly(data, period_end=True)
        assert isinstance(monthly, pd.DataFrame)
        assert len(monthly) == 1
        assert monthly.iloc[0]['Open'] == 100.0
        assert monthly.iloc[0]['High'] == 102.0
        assert monthly.iloc[0]['Low'] == 99.0
        assert monthly.iloc[0]['Close'] == 101.0
        assert monthly.iloc[0]['Volume'] == 1000000

    def test_data_with_gaps(self, data_with_gaps):
        """Should handle data with gaps (weekends, holidays) correctly."""
        from tradingagents.dataflows.multi_timeframe import aggregate_to_weekly, aggregate_to_monthly

        # Weekly aggregation should work with gaps
        weekly = aggregate_to_weekly(data_with_gaps, anchor='SUN')
        assert isinstance(weekly, pd.DataFrame)
        assert len(weekly) > 0

        # Volume should be preserved despite gaps
        assert weekly['Volume'].sum() == data_with_gaps['Volume'].sum()

        # Monthly aggregation should work with gaps
        monthly = aggregate_to_monthly(data_with_gaps, period_end=True)
        assert isinstance(monthly, pd.DataFrame)
        assert len(monthly) == 1  # All data in January

        # Verify aggregation accuracy
        assert monthly.iloc[0]['Open'] == data_with_gaps.iloc[0]['Open']
        assert monthly.iloc[0]['Close'] == data_with_gaps.iloc[-1]['Close']
        assert monthly.iloc[0]['High'] == data_with_gaps['High'].max()
        assert monthly.iloc[0]['Low'] == data_with_gaps['Low'].min()
        assert monthly.iloc[0]['Volume'] == data_with_gaps['Volume'].sum()

    def test_multiple_months_with_gaps(self):
        """Should handle multiple months with gaps correctly."""
        from tradingagents.dataflows.multi_timeframe import aggregate_to_monthly

        # Create 3 months of business days only
        dates = pd.bdate_range('2024-01-01', '2024-03-31', freq='B')
        data = pd.DataFrame({
            'Open': [100.0 + i * 0.1 for i in range(len(dates))],
            'High': [102.0 + i * 0.1 for i in range(len(dates))],
            'Low': [99.0 + i * 0.1 for i in range(len(dates))],
            'Close': [101.0 + i * 0.1 for i in range(len(dates))],
            'Volume': [1000000 + i * 1000 for i in range(len(dates))],
        }, index=dates)

        result = aggregate_to_monthly(data, period_end=True)

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 3  # Jan, Feb, Mar

        # Each month should have correct aggregations
        for i in range(len(result)):
            month_data = data[data.index.month == (i + 1)]
            assert result.iloc[i]['Open'] == month_data.iloc[0]['Open']
            assert result.iloc[i]['Close'] == month_data.iloc[-1]['Close']
            assert result.iloc[i]['High'] == month_data['High'].max()
            assert result.iloc[i]['Low'] == month_data['Low'].min()
            assert result.iloc[i]['Volume'] == month_data['Volume'].sum()

    def test_intraday_to_daily_aggregation(self):
        """Should handle intraday data aggregation to daily."""
        from tradingagents.dataflows.multi_timeframe import _resample_ohlcv

        # Create 1 day of hourly data (9:30 AM to 4:00 PM = 7 hours)
        dates = pd.date_range('2024-01-15 09:30', periods=7, freq='h')
        data = pd.DataFrame({
            'Open': [100.0, 101.0, 100.5, 102.0, 101.5, 103.0, 102.5],
            'High': [101.5, 102.0, 101.5, 103.0, 102.5, 104.0, 103.5],
            'Low': [99.5, 100.5, 100.0, 101.5, 101.0, 102.5, 102.0],
            'Close': [101.0, 100.5, 102.0, 101.5, 103.0, 102.5, 103.5],
            'Volume': [100000, 150000, 120000, 180000, 140000, 160000, 110000],
        }, index=dates)

        # Aggregate to daily using 'D' frequency
        result = _resample_ohlcv(data, freq='D', label='right', closed='right')

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 1

        # Verify daily aggregation
        assert result.iloc[0]['Open'] == 100.0   # First hour's open
        assert result.iloc[0]['High'] == 104.0   # Max of all hours
        assert result.iloc[0]['Low'] == 99.5     # Min of all hours
        assert result.iloc[0]['Close'] == 103.5  # Last hour's close
        assert result.iloc[0]['Volume'] == 960000  # Sum of all hours

    def test_chained_aggregations(self):
        """Should support chaining aggregations (daily -> weekly -> monthly)."""
        from tradingagents.dataflows.multi_timeframe import aggregate_to_weekly, aggregate_to_monthly

        # Create 60 days of daily data
        dates = pd.date_range('2024-01-01', periods=60, freq='D')
        data = pd.DataFrame({
            'Open': [100.0 + i * 0.1 for i in range(60)],
            'High': [102.0 + i * 0.1 for i in range(60)],
            'Low': [99.0 + i * 0.1 for i in range(60)],
            'Close': [101.0 + i * 0.1 for i in range(60)],
            'Volume': [1000000 + i * 1000 for i in range(60)],
        }, index=dates)

        original_volume = data['Volume'].sum()

        # Daily -> Weekly
        weekly = aggregate_to_weekly(data, anchor='SUN')
        assert isinstance(weekly, pd.DataFrame)
        assert weekly['Volume'].sum() == original_volume

        # Weekly -> Monthly (aggregate weekly data to monthly)
        monthly = aggregate_to_monthly(weekly, period_end=True)
        assert isinstance(monthly, pd.DataFrame)
        assert monthly['Volume'].sum() == original_volume

        # Verify monthly matches direct daily -> monthly
        monthly_direct = aggregate_to_monthly(data, period_end=True)
        assert isinstance(monthly_direct, pd.DataFrame)

        # Both paths should preserve total volume
        assert monthly['Volume'].sum() == monthly_direct['Volume'].sum()

    def test_empty_result_handling(self):
        """Should handle cases where resampling produces empty results."""
        from tradingagents.dataflows.multi_timeframe import aggregate_to_weekly

        # Create data with only NaN values
        dates = pd.date_range('2024-01-01', periods=7, freq='D')
        data = pd.DataFrame({
            'Open': [np.nan] * 7,
            'High': [np.nan] * 7,
            'Low': [np.nan] * 7,
            'Close': [np.nan] * 7,
            'Volume': [0] * 7,
        }, index=dates)

        result = aggregate_to_weekly(data, anchor='SUN')

        # Should still return a DataFrame (even if values are NaN)
        assert isinstance(result, pd.DataFrame)

    def test_mixed_frequency_data(self):
        """Should handle data with mixed frequencies (some days missing)."""
        from tradingagents.dataflows.multi_timeframe import aggregate_to_weekly

        # Create irregular dates (not every day)
        dates = pd.to_datetime([
            '2024-01-01', '2024-01-02', '2024-01-04',  # Missing Jan 3
            '2024-01-08', '2024-01-09',                # Missing Jan 5-7
            '2024-01-15', '2024-01-16'                 # Missing Jan 10-14
        ])

        data = pd.DataFrame({
            'Open': [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0],
            'High': [102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0],
            'Low': [99.0, 100.0, 101.0, 102.0, 103.0, 104.0, 105.0],
            'Close': [101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0],
            'Volume': [1000000, 1100000, 1200000, 1300000, 1400000, 1500000, 1600000],
        }, index=dates)

        result = aggregate_to_weekly(data, anchor='SUN')

        assert isinstance(result, pd.DataFrame)
        assert len(result) > 0

        # Volume should be preserved
        assert result['Volume'].sum() == data['Volume'].sum()

    def test_leap_year_february(self):
        """Should handle February in leap year correctly."""
        from tradingagents.dataflows.multi_timeframe import aggregate_to_monthly

        # 2024 is a leap year (29 days in Feb)
        dates = pd.date_range('2024-02-01', '2024-02-29', freq='D')
        data = pd.DataFrame({
            'Open': [100.0 + i * 0.1 for i in range(len(dates))],
            'High': [102.0 + i * 0.1 for i in range(len(dates))],
            'Low': [99.0 + i * 0.1 for i in range(len(dates))],
            'Close': [101.0 + i * 0.1 for i in range(len(dates))],
            'Volume': [1000000 + i * 1000 for i in range(len(dates))],
        }, index=dates)

        result = aggregate_to_monthly(data, period_end=True)

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 1
        assert result.index[0].day == 29  # Should end on Feb 29

        # Verify aggregation
        assert result.iloc[0]['Open'] == data.iloc[0]['Open']
        assert result.iloc[0]['Close'] == data.iloc[-1]['Close']
        assert result.iloc[0]['Volume'] == data['Volume'].sum()

    def test_year_end_rollover(self):
        """Should handle year-end rollover correctly."""
        from tradingagents.dataflows.multi_timeframe import aggregate_to_weekly, aggregate_to_monthly

        # Create data spanning year boundary
        dates = pd.date_range('2023-12-25', '2024-01-05', freq='D')
        data = pd.DataFrame({
            'Open': [100.0 + i * 0.1 for i in range(len(dates))],
            'High': [102.0 + i * 0.1 for i in range(len(dates))],
            'Low': [99.0 + i * 0.1 for i in range(len(dates))],
            'Close': [101.0 + i * 0.1 for i in range(len(dates))],
            'Volume': [1000000 + i * 1000 for i in range(len(dates))],
        }, index=dates)

        # Weekly aggregation
        weekly = aggregate_to_weekly(data, anchor='SUN')
        assert isinstance(weekly, pd.DataFrame)
        assert weekly['Volume'].sum() == data['Volume'].sum()

        # Monthly aggregation
        monthly = aggregate_to_monthly(data, period_end=True)
        assert isinstance(monthly, pd.DataFrame)
        assert len(monthly) == 2  # December and January
        assert monthly['Volume'].sum() == data['Volume'].sum()
