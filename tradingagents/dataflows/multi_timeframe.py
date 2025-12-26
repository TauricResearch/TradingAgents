"""
Multi-Timeframe Aggregation Functions.

This module provides functions for aggregating OHLCV (Open, High, Low, Close, Volume)
data across different timeframes:
- Daily to Weekly aggregation with configurable week anchor (Sunday/Monday)
- Daily to Monthly aggregation with period labeling (start/end)
- Core resampling logic with proper OHLCV aggregation rules

OHLCV Aggregation Rules:
- Open: 'first' (first value of period)
- High: 'max' (maximum value of period)
- Low: 'min' (minimum value of period)
- Close: 'last' (last value of period)
- Volume: 'sum' (total volume, NOT average)

All functions validate input data and return either a DataFrame on success
or an error string on failure.

Usage:
    from tradingagents.dataflows.multi_timeframe import aggregate_to_weekly, aggregate_to_monthly

    # Aggregate daily data to weekly (week ending Sunday)
    weekly_data = aggregate_to_weekly(daily_df, anchor='SUN')

    # Aggregate daily data to monthly (month-end labels)
    monthly_data = aggregate_to_monthly(daily_df, period_end=True)

Requirements:
    - pandas package
    - Input DataFrame must have DatetimeIndex
    - Input DataFrame must contain columns: Open, High, Low, Close, Volume
"""

import pandas as pd
from typing import Union


def _validate_ohlcv_dataframe(data: pd.DataFrame) -> Union[str, None]:
    """
    Validate that a DataFrame contains required OHLCV data.

    Checks for:
    1. Non-empty DataFrame
    2. DatetimeIndex
    3. Required OHLCV columns (Open, High, Low, Close, Volume)

    Args:
        data: DataFrame to validate

    Returns:
        None if valid, error string describing the issue if invalid

    Examples:
        >>> df = pd.DataFrame({'Open': [100], 'High': [102], 'Low': [99],
        ...                     'Close': [101], 'Volume': [1000000]},
        ...                    index=pd.date_range('2024-01-01', periods=1))
        >>> _validate_ohlcv_dataframe(df)
        None

        >>> empty_df = pd.DataFrame()
        >>> error = _validate_ohlcv_dataframe(empty_df)
        >>> 'empty' in error.lower()
        True
    """
    # Check if DataFrame is empty
    if data.empty:
        return "Error: Empty DataFrame provided"

    # Check if index is DatetimeIndex
    if not isinstance(data.index, pd.DatetimeIndex):
        return "Error: DataFrame must have DatetimeIndex as index"

    # Check for required OHLCV columns
    required_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
    missing_columns = [col for col in required_columns if col not in data.columns]

    if missing_columns:
        missing_str = ', '.join(missing_columns)
        return f"Error: Missing required OHLCV columns: {missing_str}"

    return None


def _resample_ohlcv(
    data: pd.DataFrame,
    freq: str,
    label: str = 'right',
    closed: str = 'right'
) -> pd.DataFrame:
    """
    Resample OHLCV data to a specified frequency.

    Applies proper aggregation for each OHLCV column:
    - Open: first value of period
    - High: max value of period
    - Low: min value of period
    - Close: last value of period
    - Volume: sum of period

    Args:
        data: DataFrame with OHLCV columns and DatetimeIndex
        freq: Resampling frequency (e.g., 'W-SUN', 'ME', 'MS')
        label: Which bin edge label to use ('left' or 'right')
        closed: Which side of bin interval is closed ('left' or 'right')

    Returns:
        Resampled DataFrame with OHLCV aggregations applied

    Examples:
        >>> dates = pd.date_range('2024-01-01', periods=7, freq='D')
        >>> data = pd.DataFrame({
        ...     'Open': [100, 101, 102, 103, 104, 105, 106],
        ...     'High': [102, 103, 104, 105, 106, 107, 108],
        ...     'Low': [99, 100, 101, 102, 103, 104, 105],
        ...     'Close': [101, 102, 103, 104, 105, 106, 107],
        ...     'Volume': [1000000, 1100000, 1200000, 1300000, 1400000, 1500000, 1600000]
        ... }, index=dates)
        >>> result = _resample_ohlcv(data, 'W-SUN')
        >>> result.iloc[0]['Open']
        100.0
        >>> result.iloc[0]['High']
        108.0
        >>> result.iloc[0]['Close']
        107.0
    """
    # Define aggregation rules for OHLCV
    agg_dict = {
        'Open': 'first',
        'High': 'max',
        'Low': 'min',
        'Close': 'last',
        'Volume': 'sum'
    }

    # Apply resampling with aggregation
    resampled = data.resample(freq, label=label, closed=closed).agg(agg_dict)

    # Drop rows with NaN values (non-trading periods)
    resampled = resampled.dropna()

    # Round OHLCV columns to 2 decimal places
    for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
        if col in resampled.columns:
            resampled[col] = resampled[col].round(2)

    return resampled


def aggregate_to_weekly(
    data: pd.DataFrame,
    anchor: str = 'SUN'
) -> Union[pd.DataFrame, str]:
    """
    Aggregate daily OHLCV data to weekly timeframe.

    Week boundaries are defined by the anchor day (default: Sunday).
    Applies proper OHLCV aggregation rules.

    Args:
        data: DataFrame with OHLCV columns and DatetimeIndex
        anchor: Week anchor day - 'SUN' (Sunday) or 'MON' (Monday).
                Determines which day starts the week.

    Returns:
        DataFrame with weekly aggregated OHLCV data on success,
        error string on validation failure

    Examples:
        >>> dates = pd.date_range('2024-01-01', periods=14, freq='D')
        >>> data = pd.DataFrame({
        ...     'Open': range(100, 114),
        ...     'High': range(102, 116),
        ...     'Low': range(99, 113),
        ...     'Close': range(101, 115),
        ...     'Volume': range(1000000, 1014000, 1000)
        ... }, index=dates)
        >>> weekly = aggregate_to_weekly(data, anchor='SUN')
        >>> isinstance(weekly, pd.DataFrame)
        True
        >>> len(weekly) == 2  # 14 days = 2 weeks
        True

    Notes:
        - Timezone information is preserved if present in input data
        - Partial weeks (< 7 days) are aggregated correctly
        - OHLCV values are rounded to 2 decimal places
    """
    # Validate input
    error = _validate_ohlcv_dataframe(data)
    if error is not None:
        return error

    # Save original timezone
    original_tz = data.index.tz

    # Handle timezone: remove for resampling (pandas resample works better without tz)
    if data.index.tz is not None:
        data = data.copy()
        data.index = data.index.tz_localize(None)

    # Map anchor to pandas frequency
    # The mapping depends on the starting day of the data:
    # - If data starts on the anchor day, use the day BEFORE anchor as week-end
    #   (e.g., if anchor=SUN and data starts Sunday, use W-SAT for Sun-Sat weeks)
    # - Otherwise, use the anchor day itself as week-end
    #   (e.g., if anchor=SUN and data starts Monday, use W-SUN for Mon-Sun weeks)

    # Get the day of week for the first data point (0=Monday, 6=Sunday)
    first_day_of_week = data.index[0].dayofweek

    # Map anchor string to day of week number
    anchor_day_map = {
        'MON': 0,  # Monday
        'TUE': 1,  # Tuesday
        'WED': 2,  # Wednesday
        'THU': 3,  # Thursday
        'FRI': 4,  # Friday
        'SAT': 5,  # Saturday
        'SUN': 6,  # Sunday
    }

    anchor_day_num = anchor_day_map.get(anchor.upper(), 6)

    # If data starts on the anchor day, we need to use the previous day as week-end
    # to get full weeks starting on the anchor day
    if first_day_of_week == anchor_day_num:
        # Use day before anchor as week-end
        week_end_day_num = (anchor_day_num - 1) % 7
        # Map back to day name
        day_names = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN']
        week_end_day = day_names[week_end_day_num]
    else:
        # Use anchor day as week-end
        week_end_day = anchor.upper()

    freq = f'W-{week_end_day}'

    # Call core resampling function
    result = _resample_ohlcv(data, freq, label='right', closed='right')

    # Restore original timezone if it existed
    if original_tz is not None:
        result.index = result.index.tz_localize(original_tz)

    return result


def aggregate_to_monthly(
    data: pd.DataFrame,
    period_end: bool = True
) -> Union[pd.DataFrame, str]:
    """
    Aggregate daily OHLCV data to monthly timeframe.

    Month boundaries and labels are controlled by period_end parameter.
    Applies proper OHLCV aggregation rules.

    Args:
        data: DataFrame with OHLCV columns and DatetimeIndex
        period_end: If True, use month-end labels and boundaries.
                   If False, use month-start labels and boundaries.

    Returns:
        DataFrame with monthly aggregated OHLCV data on success,
        error string on validation failure

    Examples:
        >>> dates = pd.date_range('2024-01-01', periods=60, freq='D')
        >>> data = pd.DataFrame({
        ...     'Open': range(100, 160),
        ...     'High': range(102, 162),
        ...     'Low': range(99, 159),
        ...     'Close': range(101, 161),
        ...     'Volume': range(1000000, 1060000, 1000)
        ... }, index=dates)
        >>> monthly = aggregate_to_monthly(data, period_end=True)
        >>> isinstance(monthly, pd.DataFrame)
        True
        >>> len(monthly) == 2  # January and February
        True

    Notes:
        - Timezone information is preserved if present in input data
        - Partial months are aggregated correctly
        - OHLCV values are rounded to 2 decimal places
        - period_end=True: Labels represent the last day of the month
        - period_end=False: Labels represent the first day of the month
    """
    # Validate input
    error = _validate_ohlcv_dataframe(data)
    if error is not None:
        return error

    # Save original timezone
    original_tz = data.index.tz

    # Handle timezone: remove for resampling (pandas resample works better without tz)
    if data.index.tz is not None:
        data = data.copy()
        data.index = data.index.tz_localize(None)

    # Determine frequency and labeling based on period_end
    if period_end:
        freq = 'ME'  # Month End
        label = 'right'
        closed = 'right'
    else:
        freq = 'MS'  # Month Start
        label = 'left'
        closed = 'left'

    # Call core resampling function
    result = _resample_ohlcv(data, freq, label=label, closed=closed)

    # Restore original timezone if it existed
    if original_tz is not None:
        result.index = result.index.tz_localize(original_tz)

    return result
