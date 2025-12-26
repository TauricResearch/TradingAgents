"""
Test suite for Multi-Timeframe Aggregation Functions (multi_timeframe.py).

This module tests:
1. _validate_ohlcv_dataframe() - Input validation for OHLCV data
2. aggregate_to_weekly() - Daily to weekly aggregation with configurable anchor
3. aggregate_to_monthly() - Daily to monthly aggregation with period labeling
4. _resample_ohlcv() - Core resampling logic for OHLCV data

Test Coverage:
- Unit tests for each function
- OHLCV aggregation rules (Open=first, High=max, Low=min, Close=last, Volume=sum)
- Week anchor handling (Sunday, Monday)
- Month label handling (period start vs period end)
- Edge cases (partial periods, single day, empty data)
- Validation (missing columns, wrong index type, empty dataframes)
- Numeric precision (2 decimal places for OHLC)

OHLCV Aggregation Rules:
- Open: 'first' (first value of period)
- High: 'max' (maximum of period)
- Low: 'min' (minimum of period)
- Close: 'last' (last value of period)
- Volume: 'sum' (total volume, NOT mean)
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

pytestmark = pytest.mark.unit


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sample_daily_ohlcv():
    """
    Create 30 days of sample daily OHLCV data for January 2024.

    Returns a DataFrame with DatetimeIndex and columns: Open, High, Low, Close, Volume.
    Each day has distinct values to verify aggregation logic.
    """
    dates = pd.date_range('2024-01-01', periods=30, freq='D')

    # Generate realistic OHLCV data with variation
    data = []
    base_price = 100.0

    for i, date in enumerate(dates):
        open_price = base_price + i * 0.5
        high_price = open_price + 2.0 + (i % 3) * 0.5
        low_price = open_price - 1.5 - (i % 2) * 0.3
        close_price = open_price + 0.5 + (i % 5) * 0.2
        volume = 1000000 + i * 10000

        data.append({
            'Open': round(open_price, 2),
            'High': round(high_price, 2),
            'Low': round(low_price, 2),
            'Close': round(close_price, 2),
            'Volume': volume
        })

    df = pd.DataFrame(data, index=dates)
    return df


@pytest.fixture
def empty_dataframe():
    """Create empty DataFrame for validation testing."""
    return pd.DataFrame()


@pytest.fixture
def missing_volume_data():
    """Create OHLC DataFrame without Volume column."""
    dates = pd.date_range('2024-01-01', periods=5, freq='D')
    return pd.DataFrame({
        'Open': [100.0, 101.0, 102.0, 103.0, 104.0],
        'High': [102.0, 103.0, 104.0, 105.0, 106.0],
        'Low': [99.0, 100.0, 101.0, 102.0, 103.0],
        'Close': [101.0, 102.0, 103.0, 104.0, 105.0],
    }, index=dates)


@pytest.fixture
def no_datetime_index_data():
    """Create DataFrame with integer index instead of DatetimeIndex."""
    return pd.DataFrame({
        'Open': [100.0, 101.0, 102.0],
        'High': [102.0, 103.0, 104.0],
        'Low': [99.0, 100.0, 101.0],
        'Close': [101.0, 102.0, 103.0],
        'Volume': [1000000, 1100000, 1200000],
    })


@pytest.fixture
def partial_week_data():
    """Create 3 days of OHLCV data (incomplete week)."""
    dates = pd.date_range('2024-01-01', periods=3, freq='D')
    return pd.DataFrame({
        'Open': [100.0, 101.0, 102.0],
        'High': [102.0, 103.0, 104.0],
        'Low': [99.0, 100.0, 101.0],
        'Close': [101.0, 102.0, 103.0],
        'Volume': [1000000, 1100000, 1200000],
    }, index=dates)


@pytest.fixture
def single_day_data():
    """Create 1 day of OHLCV data."""
    dates = pd.date_range('2024-01-15', periods=1, freq='D')
    return pd.DataFrame({
        'Open': [100.0],
        'High': [102.0],
        'Low': [99.0],
        'Close': [101.0],
        'Volume': [1000000],
    }, index=dates)


@pytest.fixture
def data_with_extra_columns():
    """Create OHLCV data with extra columns that should be ignored."""
    dates = pd.date_range('2024-01-01', periods=5, freq='D')
    return pd.DataFrame({
        'Open': [100.0, 101.0, 102.0, 103.0, 104.0],
        'High': [102.0, 103.0, 104.0, 105.0, 106.0],
        'Low': [99.0, 100.0, 101.0, 102.0, 103.0],
        'Close': [101.0, 102.0, 103.0, 104.0, 105.0],
        'Volume': [1000000, 1100000, 1200000, 1300000, 1400000],
        'ExtraColumn1': [1, 2, 3, 4, 5],
        'ExtraColumn2': ['a', 'b', 'c', 'd', 'e'],
    }, index=dates)


# ============================================================================
# Test _validate_ohlcv_dataframe()
# ============================================================================

class TestValidation:
    """Test input validation for OHLCV dataframes."""

    def test_empty_dataframe_returns_error(self, empty_dataframe):
        """Empty DataFrame should return validation error."""
        from tradingagents.dataflows.multi_timeframe import _validate_ohlcv_dataframe

        error = _validate_ohlcv_dataframe(empty_dataframe)

        assert error is not None
        assert isinstance(error, str)
        assert 'empty' in error.lower() or 'no data' in error.lower()

    def test_missing_datetime_index_returns_error(self, no_datetime_index_data):
        """DataFrame without DatetimeIndex should return validation error."""
        from tradingagents.dataflows.multi_timeframe import _validate_ohlcv_dataframe

        error = _validate_ohlcv_dataframe(no_datetime_index_data)

        assert error is not None
        assert isinstance(error, str)
        assert 'datetime' in error.lower() or 'index' in error.lower()

    def test_missing_volume_column_returns_error(self, missing_volume_data):
        """DataFrame without Volume column should return validation error."""
        from tradingagents.dataflows.multi_timeframe import _validate_ohlcv_dataframe

        error = _validate_ohlcv_dataframe(missing_volume_data)

        assert error is not None
        assert isinstance(error, str)
        assert 'volume' in error.lower()

    def test_missing_ohlcv_columns_returns_error(self):
        """DataFrame missing any OHLC column should return validation error."""
        from tradingagents.dataflows.multi_timeframe import _validate_ohlcv_dataframe

        dates = pd.date_range('2024-01-01', periods=5, freq='D')

        # Test missing Open
        df_no_open = pd.DataFrame({
            'High': [102.0, 103.0, 104.0, 105.0, 106.0],
            'Low': [99.0, 100.0, 101.0, 102.0, 103.0],
            'Close': [101.0, 102.0, 103.0, 104.0, 105.0],
            'Volume': [1000000, 1100000, 1200000, 1300000, 1400000],
        }, index=dates)

        error = _validate_ohlcv_dataframe(df_no_open)
        assert error is not None
        assert 'open' in error.lower()

        # Test missing High
        df_no_high = pd.DataFrame({
            'Open': [100.0, 101.0, 102.0, 103.0, 104.0],
            'Low': [99.0, 100.0, 101.0, 102.0, 103.0],
            'Close': [101.0, 102.0, 103.0, 104.0, 105.0],
            'Volume': [1000000, 1100000, 1200000, 1300000, 1400000],
        }, index=dates)

        error = _validate_ohlcv_dataframe(df_no_high)
        assert error is not None
        assert 'high' in error.lower()

        # Test missing Low
        df_no_low = pd.DataFrame({
            'Open': [100.0, 101.0, 102.0, 103.0, 104.0],
            'High': [102.0, 103.0, 104.0, 105.0, 106.0],
            'Close': [101.0, 102.0, 103.0, 104.0, 105.0],
            'Volume': [1000000, 1100000, 1200000, 1300000, 1400000],
        }, index=dates)

        error = _validate_ohlcv_dataframe(df_no_low)
        assert error is not None
        assert 'low' in error.lower()

        # Test missing Close
        df_no_close = pd.DataFrame({
            'Open': [100.0, 101.0, 102.0, 103.0, 104.0],
            'High': [102.0, 103.0, 104.0, 105.0, 106.0],
            'Low': [99.0, 100.0, 101.0, 102.0, 103.0],
            'Volume': [1000000, 1100000, 1200000, 1300000, 1400000],
        }, index=dates)

        error = _validate_ohlcv_dataframe(df_no_close)
        assert error is not None
        assert 'close' in error.lower()

    def test_valid_dataframe_returns_none(self, sample_daily_ohlcv):
        """Valid OHLCV DataFrame should return None (no error)."""
        from tradingagents.dataflows.multi_timeframe import _validate_ohlcv_dataframe

        error = _validate_ohlcv_dataframe(sample_daily_ohlcv)

        assert error is None

    def test_extra_columns_ignored(self, data_with_extra_columns):
        """DataFrame with extra columns should be valid (extras ignored)."""
        from tradingagents.dataflows.multi_timeframe import _validate_ohlcv_dataframe

        error = _validate_ohlcv_dataframe(data_with_extra_columns)

        assert error is None


# ============================================================================
# Test aggregate_to_weekly()
# ============================================================================

class TestWeeklyAggregation:
    """Test weekly aggregation from daily OHLCV data."""

    def test_weekly_open_is_first_day(self, sample_daily_ohlcv):
        """Weekly Open should be the first day's Open of the week."""
        from tradingagents.dataflows.multi_timeframe import aggregate_to_weekly

        result = aggregate_to_weekly(sample_daily_ohlcv, anchor='SUN')

        # Should not be an error string
        assert isinstance(result, pd.DataFrame)

        # Check first week's Open matches first day in that week
        # Jan 1, 2024 is a Monday, with Sunday anchor first week starts Dec 31, 2023
        # We'll verify Open is from the first available day in each period
        first_week_open = result.iloc[0]['Open']
        assert first_week_open == sample_daily_ohlcv.iloc[0]['Open']

    def test_weekly_high_is_max_of_period(self, sample_daily_ohlcv):
        """Weekly High should be the maximum High of all days in the week."""
        from tradingagents.dataflows.multi_timeframe import aggregate_to_weekly

        result = aggregate_to_weekly(sample_daily_ohlcv, anchor='SUN')

        assert isinstance(result, pd.DataFrame)

        # First week should have High equal to max of first 7 days' High values
        first_week_high = result.iloc[0]['High']
        expected_high = sample_daily_ohlcv.iloc[0:7]['High'].max()

        assert first_week_high == expected_high

    def test_weekly_low_is_min_of_period(self, sample_daily_ohlcv):
        """Weekly Low should be the minimum Low of all days in the week."""
        from tradingagents.dataflows.multi_timeframe import aggregate_to_weekly

        result = aggregate_to_weekly(sample_daily_ohlcv, anchor='SUN')

        assert isinstance(result, pd.DataFrame)

        # First week should have Low equal to min of first 7 days' Low values
        first_week_low = result.iloc[0]['Low']
        expected_low = sample_daily_ohlcv.iloc[0:7]['Low'].min()

        assert first_week_low == expected_low

    def test_weekly_close_is_last_day(self, sample_daily_ohlcv):
        """Weekly Close should be the last day's Close of the week."""
        from tradingagents.dataflows.multi_timeframe import aggregate_to_weekly

        result = aggregate_to_weekly(sample_daily_ohlcv, anchor='SUN')

        assert isinstance(result, pd.DataFrame)

        # Last week's Close should be from last day in dataset
        last_week_close = result.iloc[-1]['Close']
        last_day_close = sample_daily_ohlcv.iloc[-1]['Close']

        assert last_week_close == last_day_close

    def test_weekly_volume_is_sum(self, sample_daily_ohlcv):
        """Weekly Volume should be the sum of all days' Volume in the week."""
        from tradingagents.dataflows.multi_timeframe import aggregate_to_weekly

        result = aggregate_to_weekly(sample_daily_ohlcv, anchor='SUN')

        assert isinstance(result, pd.DataFrame)

        # First week should have Volume equal to sum of first 7 days' Volume
        first_week_volume = result.iloc[0]['Volume']
        expected_volume = sample_daily_ohlcv.iloc[0:7]['Volume'].sum()

        assert first_week_volume == expected_volume

    def test_partial_week_handling(self, partial_week_data):
        """Should handle partial week (< 7 days) correctly."""
        from tradingagents.dataflows.multi_timeframe import aggregate_to_weekly

        result = aggregate_to_weekly(partial_week_data, anchor='SUN')

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 1  # Should create 1 week from 3 days

        # Verify aggregation still works correctly
        assert result.iloc[0]['Open'] == partial_week_data.iloc[0]['Open']
        assert result.iloc[0]['Close'] == partial_week_data.iloc[-1]['Close']
        assert result.iloc[0]['High'] == partial_week_data['High'].max()
        assert result.iloc[0]['Low'] == partial_week_data['Low'].min()
        assert result.iloc[0]['Volume'] == partial_week_data['Volume'].sum()

    def test_week_anchor_sunday(self):
        """Week anchor='SUN' should start weeks on Sunday."""
        from tradingagents.dataflows.multi_timeframe import aggregate_to_weekly

        # Create data starting on a known Sunday
        dates = pd.date_range('2024-01-07', periods=14, freq='D')  # Jan 7 is Sunday
        data = pd.DataFrame({
            'Open': range(100, 114),
            'High': range(102, 116),
            'Low': range(99, 113),
            'Close': range(101, 115),
            'Volume': range(1000000, 1014000, 1000),
        }, index=dates)

        result = aggregate_to_weekly(data, anchor='SUN')

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 2  # 14 days = 2 full weeks starting Sunday

    def test_week_anchor_monday(self):
        """Week anchor='MON' should start weeks on Monday."""
        from tradingagents.dataflows.multi_timeframe import aggregate_to_weekly

        # Create data starting on a known Monday
        dates = pd.date_range('2024-01-01', periods=14, freq='D')  # Jan 1 is Monday
        data = pd.DataFrame({
            'Open': range(100, 114),
            'High': range(102, 116),
            'Low': range(99, 113),
            'Close': range(101, 115),
            'Volume': range(1000000, 1014000, 1000),
        }, index=dates)

        result = aggregate_to_weekly(data, anchor='MON')

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 2  # 14 days = 2 full weeks starting Monday

    def test_numeric_rounding_to_2_decimals(self):
        """OHLC values should be rounded to 2 decimal places."""
        from tradingagents.dataflows.multi_timeframe import aggregate_to_weekly

        dates = pd.date_range('2024-01-01', periods=7, freq='D')
        data = pd.DataFrame({
            'Open': [100.123, 100.456, 100.789, 101.111, 101.222, 101.333, 101.444],
            'High': [102.567, 102.678, 102.789, 102.891, 102.912, 102.934, 102.956],
            'Low': [99.111, 99.222, 99.333, 99.444, 99.555, 99.666, 99.777],
            'Close': [101.234, 101.345, 101.456, 101.567, 101.678, 101.789, 101.891],
            'Volume': [1000000, 1100000, 1200000, 1300000, 1400000, 1500000, 1600000],
        }, index=dates)

        result = aggregate_to_weekly(data, anchor='SUN')

        assert isinstance(result, pd.DataFrame)

        # Check all OHLC values have max 2 decimal places
        for col in ['Open', 'High', 'Low', 'Close']:
            for value in result[col]:
                # Convert to string and check decimal places
                decimal_places = len(str(value).split('.')[-1]) if '.' in str(value) else 0
                assert decimal_places <= 2, f"{col} value {value} has more than 2 decimal places"

    def test_returns_error_string_on_invalid_input(self, empty_dataframe):
        """Should return error string for invalid input."""
        from tradingagents.dataflows.multi_timeframe import aggregate_to_weekly

        result = aggregate_to_weekly(empty_dataframe)

        assert isinstance(result, str)
        assert 'error' in result.lower() or 'empty' in result.lower()


# ============================================================================
# Test aggregate_to_monthly()
# ============================================================================

class TestMonthlyAggregation:
    """Test monthly aggregation from daily OHLCV data."""

    def test_monthly_open_is_first_day(self, sample_daily_ohlcv):
        """Monthly Open should be the first day's Open of the month."""
        from tradingagents.dataflows.multi_timeframe import aggregate_to_monthly

        result = aggregate_to_monthly(sample_daily_ohlcv, period_end=True)

        assert isinstance(result, pd.DataFrame)

        # First month's Open should match first day's Open
        first_month_open = result.iloc[0]['Open']
        assert first_month_open == sample_daily_ohlcv.iloc[0]['Open']

    def test_monthly_high_is_max(self, sample_daily_ohlcv):
        """Monthly High should be the maximum High of all days in the month."""
        from tradingagents.dataflows.multi_timeframe import aggregate_to_monthly

        result = aggregate_to_monthly(sample_daily_ohlcv, period_end=True)

        assert isinstance(result, pd.DataFrame)

        # Month High should be max of all days' High values
        month_high = result.iloc[0]['High']
        expected_high = sample_daily_ohlcv['High'].max()

        assert month_high == expected_high

    def test_monthly_low_is_min(self, sample_daily_ohlcv):
        """Monthly Low should be the minimum Low of all days in the month."""
        from tradingagents.dataflows.multi_timeframe import aggregate_to_monthly

        result = aggregate_to_monthly(sample_daily_ohlcv, period_end=True)

        assert isinstance(result, pd.DataFrame)

        # Month Low should be min of all days' Low values
        month_low = result.iloc[0]['Low']
        expected_low = sample_daily_ohlcv['Low'].min()

        assert month_low == expected_low

    def test_monthly_close_is_last_day(self, sample_daily_ohlcv):
        """Monthly Close should be the last day's Close of the month."""
        from tradingagents.dataflows.multi_timeframe import aggregate_to_monthly

        result = aggregate_to_monthly(sample_daily_ohlcv, period_end=True)

        assert isinstance(result, pd.DataFrame)

        # Month Close should be last day's Close
        month_close = result.iloc[0]['Close']
        last_day_close = sample_daily_ohlcv.iloc[-1]['Close']

        assert month_close == last_day_close

    def test_monthly_volume_is_sum(self, sample_daily_ohlcv):
        """Monthly Volume should be the sum of all days' Volume in the month."""
        from tradingagents.dataflows.multi_timeframe import aggregate_to_monthly

        result = aggregate_to_monthly(sample_daily_ohlcv, period_end=True)

        assert isinstance(result, pd.DataFrame)

        # Month Volume should be sum of all days' Volume
        month_volume = result.iloc[0]['Volume']
        expected_volume = sample_daily_ohlcv['Volume'].sum()

        assert month_volume == expected_volume

    def test_month_end_label(self):
        """period_end=True should label periods with end date."""
        from tradingagents.dataflows.multi_timeframe import aggregate_to_monthly

        # Create 2 months of data
        dates = pd.date_range('2024-01-01', '2024-02-29', freq='D')
        data = pd.DataFrame({
            'Open': range(100, 100 + len(dates)),
            'High': range(102, 102 + len(dates)),
            'Low': range(99, 99 + len(dates)),
            'Close': range(101, 101 + len(dates)),
            'Volume': range(1000000, 1000000 + len(dates) * 1000, 1000),
        }, index=dates)

        result = aggregate_to_monthly(data, period_end=True)

        assert isinstance(result, pd.DataFrame)

        # Index should be at month end
        assert result.index[0].day == 31  # Jan 31
        assert result.index[1].day == 29  # Feb 29 (2024 is leap year)

    def test_month_start_label(self):
        """period_end=False should label periods with start date."""
        from tradingagents.dataflows.multi_timeframe import aggregate_to_monthly

        # Create 2 months of data
        dates = pd.date_range('2024-01-01', '2024-02-29', freq='D')
        data = pd.DataFrame({
            'Open': range(100, 100 + len(dates)),
            'High': range(102, 102 + len(dates)),
            'Low': range(99, 99 + len(dates)),
            'Close': range(101, 101 + len(dates)),
            'Volume': range(1000000, 1000000 + len(dates) * 1000, 1000),
        }, index=dates)

        result = aggregate_to_monthly(data, period_end=False)

        assert isinstance(result, pd.DataFrame)

        # Index should be at month start
        assert result.index[0].day == 1  # Jan 1
        assert result.index[1].day == 1  # Feb 1

    def test_partial_month_handling(self):
        """Should handle partial month (< full month days) correctly."""
        from tradingagents.dataflows.multi_timeframe import aggregate_to_monthly

        # Create 10 days in January
        dates = pd.date_range('2024-01-01', periods=10, freq='D')
        data = pd.DataFrame({
            'Open': range(100, 110),
            'High': range(102, 112),
            'Low': range(99, 109),
            'Close': range(101, 111),
            'Volume': range(1000000, 1010000, 1000),
        }, index=dates)

        result = aggregate_to_monthly(data, period_end=True)

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 1  # Should create 1 month from 10 days

        # Verify aggregation still works correctly
        assert result.iloc[0]['Open'] == data.iloc[0]['Open']
        assert result.iloc[0]['Close'] == data.iloc[-1]['Close']
        assert result.iloc[0]['High'] == data['High'].max()
        assert result.iloc[0]['Low'] == data['Low'].min()
        assert result.iloc[0]['Volume'] == data['Volume'].sum()

    def test_returns_error_string_on_invalid_input(self, no_datetime_index_data):
        """Should return error string for invalid input."""
        from tradingagents.dataflows.multi_timeframe import aggregate_to_monthly

        result = aggregate_to_monthly(no_datetime_index_data)

        assert isinstance(result, str)
        assert 'error' in result.lower() or 'datetime' in result.lower()


# ============================================================================
# Test _resample_ohlcv()
# ============================================================================

class TestResampleOHLCV:
    """Test core resampling logic for OHLCV data."""

    def test_applies_correct_aggregations(self):
        """Should apply correct aggregation for each OHLCV column."""
        from tradingagents.dataflows.multi_timeframe import _resample_ohlcv

        dates = pd.date_range('2024-01-01', periods=7, freq='D')
        data = pd.DataFrame({
            'Open': [100, 101, 102, 103, 104, 105, 106],
            'High': [102, 103, 104, 105, 106, 107, 108],
            'Low': [99, 100, 101, 102, 103, 104, 105],
            'Close': [101, 102, 103, 104, 105, 106, 107],
            'Volume': [1000000, 1100000, 1200000, 1300000, 1400000, 1500000, 1600000],
        }, index=dates)

        # Resample to weekly (W-SUN = week ending Sunday)
        result = _resample_ohlcv(data, freq='W-SUN', label='right', closed='right')

        assert isinstance(result, pd.DataFrame)

        # Verify aggregation rules
        assert result.iloc[0]['Open'] == 100  # First
        assert result.iloc[0]['High'] == 108  # Max
        assert result.iloc[0]['Low'] == 99    # Min
        assert result.iloc[0]['Close'] == 107  # Last
        assert result.iloc[0]['Volume'] == sum([1000000, 1100000, 1200000, 1300000, 1400000, 1500000, 1600000])  # Sum

    def test_rounds_ohlc_to_2_decimals(self):
        """Should round OHLC values to 2 decimal places."""
        from tradingagents.dataflows.multi_timeframe import _resample_ohlcv

        dates = pd.date_range('2024-01-01', periods=7, freq='D')
        data = pd.DataFrame({
            'Open': [100.12345] * 7,
            'High': [102.67891] * 7,
            'Low': [99.11111] * 7,
            'Close': [101.99999] * 7,
            'Volume': [1000000] * 7,
        }, index=dates)

        result = _resample_ohlcv(data, freq='W-SUN', label='right', closed='right')

        assert isinstance(result, pd.DataFrame)

        # Check rounding
        assert result.iloc[0]['Open'] == 100.12
        assert result.iloc[0]['High'] == 102.68
        assert result.iloc[0]['Low'] == 99.11
        assert result.iloc[0]['Close'] == 102.00

    def test_preserves_datetime_index(self):
        """Should preserve DatetimeIndex in result."""
        from tradingagents.dataflows.multi_timeframe import _resample_ohlcv

        dates = pd.date_range('2024-01-01', periods=7, freq='D')
        data = pd.DataFrame({
            'Open': [100] * 7,
            'High': [102] * 7,
            'Low': [99] * 7,
            'Close': [101] * 7,
            'Volume': [1000000] * 7,
        }, index=dates)

        result = _resample_ohlcv(data, freq='W-SUN', label='right', closed='right')

        assert isinstance(result.index, pd.DatetimeIndex)

    def test_handles_single_period(self, single_day_data):
        """Should handle data that results in single resampled period."""
        from tradingagents.dataflows.multi_timeframe import _resample_ohlcv

        result = _resample_ohlcv(single_day_data, freq='W-SUN', label='right', closed='right')

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 1

        # Values should match original (no aggregation needed)
        assert result.iloc[0]['Open'] == single_day_data.iloc[0]['Open']
        assert result.iloc[0]['High'] == single_day_data.iloc[0]['High']
        assert result.iloc[0]['Low'] == single_day_data.iloc[0]['Low']
        assert result.iloc[0]['Close'] == single_day_data.iloc[0]['Close']
        assert result.iloc[0]['Volume'] == single_day_data.iloc[0]['Volume']
