"""
Benchmark Data Retrieval and Analysis Functions.

This module provides functions for retrieving and analyzing benchmark data:
- Benchmark data fetching (SPY, sector ETFs)
- Relative strength calculations (IBD-style)
- Rolling correlation analysis
- Beta calculations

All functions return pandas DataFrames/Series/floats on success or error strings on failure.

Usage:
    from spektiv.dataflows.benchmark import (
        get_spy_data,
        get_sector_etf_data,
        calculate_relative_strength
    )

    # Get SPY benchmark data
    spy_data = get_spy_data('2024-01-01', '2024-12-31')

    # Get sector ETF data
    tech_data = get_sector_etf_data('technology', '2024-01-01', '2024-12-31')

    # Calculate relative strength
    rs = calculate_relative_strength(stock_data, spy_data)

Requirements:
    - yfinance package: pip install yfinance
"""

import pandas as pd
import numpy as np
from typing import Union, List
from datetime import datetime

# Try to import yfinance, but allow it to be mocked in tests
try:
    import yfinance as yf
except ImportError:
    yf = None


# ============================================================================
# SECTOR ETF Mappings
# ============================================================================

SECTOR_ETFS = {
    'communication': 'XLC',
    'consumer_discretionary': 'XLY',
    'consumer_staples': 'XLP',
    'energy': 'XLE',
    'financials': 'XLF',
    'healthcare': 'XLV',
    'industrials': 'XLI',
    'materials': 'XLB',
    'real_estate': 'XLRE',
    'technology': 'XLK',
    'utilities': 'XLU'
}


# ============================================================================
# Benchmark Data Fetching Functions
# ============================================================================

def get_benchmark_data(
    symbol: str,
    start_date: str,
    end_date: str
) -> Union[pd.DataFrame, str]:
    """
    Fetch benchmark OHLCV data via yfinance.

    Args:
        symbol: Ticker symbol (e.g., 'SPY', 'XLK')
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format

    Returns:
        pd.DataFrame with DatetimeIndex and columns: Open, High, Low, Close, Volume
        str with error message on failure

    Examples:
        >>> data = get_benchmark_data('SPY', '2024-01-01', '2024-12-31')
        >>> data = get_benchmark_data('XLK', '2024-01-01', '2024-12-31')
    """
    if yf is None:
        return "Error: yfinance package is not installed. Install with: pip install yfinance"

    try:
        # Validate date formats
        datetime.strptime(start_date, "%Y-%m-%d")
        datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError as e:
        return f"Error: Invalid date format. Use YYYY-MM-DD. Details: {str(e)}"

    try:
        # Fetch data from yfinance
        ticker = yf.Ticker(symbol)
        data = ticker.history(start=start_date, end=end_date)

        # Check if data is empty
        if data.empty:
            return f"Error: No data found for symbol '{symbol}' between {start_date} and {end_date}"

        # Remove timezone info if present
        if data.index.tz is not None:
            data.index = data.index.tz_localize(None)

        return data

    except Exception as e:
        return f"Error fetching data for {symbol}: {str(e)}"


def get_spy_data(
    start_date: str,
    end_date: str
) -> Union[pd.DataFrame, str]:
    """
    Fetch SPY benchmark data (convenience wrapper).

    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format

    Returns:
        pd.DataFrame with DatetimeIndex and columns: Open, High, Low, Close, Volume
        str with error message on failure

    Examples:
        >>> spy_data = get_spy_data('2024-01-01', '2024-12-31')
    """
    return get_benchmark_data('SPY', start_date, end_date)


def get_sector_etf_data(
    sector: str,
    start_date: str,
    end_date: str
) -> Union[pd.DataFrame, str]:
    """
    Fetch sector ETF data.

    Args:
        sector: Sector name (e.g., 'technology', 'financials', 'energy')
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format

    Returns:
        pd.DataFrame with DatetimeIndex and columns: Open, High, Low, Close, Volume
        str with error message on failure

    Valid Sectors:
        - communication (XLC)
        - consumer_discretionary (XLY)
        - consumer_staples (XLP)
        - energy (XLE)
        - financials (XLF)
        - healthcare (XLV)
        - industrials (XLI)
        - materials (XLB)
        - real_estate (XLRE)
        - technology (XLK)
        - utilities (XLU)

    Examples:
        >>> tech_data = get_sector_etf_data('technology', '2024-01-01', '2024-12-31')
        >>> finance_data = get_sector_etf_data('financials', '2024-01-01', '2024-12-31')
    """
    # Validate sector
    if sector not in SECTOR_ETFS:
        valid_sectors = ', '.join(sorted(SECTOR_ETFS.keys()))
        return f"Error: Invalid sector '{sector}'. Valid sectors: {valid_sectors}"

    # Get symbol for sector
    symbol = SECTOR_ETFS[sector]

    # Fetch data
    return get_benchmark_data(symbol, start_date, end_date)


# ============================================================================
# Relative Strength Calculation
# ============================================================================

def calculate_relative_strength(
    stock_data: pd.DataFrame,
    benchmark_data: pd.DataFrame,
    periods: List[int] = [63, 126, 189, 252]
) -> Union[float, str]:
    """
    Calculate IBD-style relative strength.

    Uses IBD formula with weighted rate of change (ROC) calculations:
    - 40% weight on 63-day (3-month) ROC
    - 20% weight on 126-day (6-month) ROC
    - 20% weight on 189-day (9-month) ROC
    - 20% weight on 252-day (12-month) ROC

    Args:
        stock_data: DataFrame with 'Close' column
        benchmark_data: DataFrame with 'Close' column
        periods: List of periods for ROC calculation (default: [63, 126, 189, 252])

    Returns:
        float: Relative strength score (stock RS - benchmark RS)
               Positive = stock outperforming benchmark
               Negative = stock underperforming benchmark
        str: Error message on failure

    Examples:
        >>> rs = calculate_relative_strength(stock_data, spy_data)
        >>> rs = calculate_relative_strength(stock_data, spy_data, periods=[20, 60, 120, 180])
    """
    # Validate inputs
    if stock_data.empty:
        return "Error: Stock data is empty"

    if benchmark_data.empty:
        return "Error: Benchmark data is empty"

    if 'Close' not in stock_data.columns:
        return "Error: Stock data missing 'Close' column"

    if 'Close' not in benchmark_data.columns:
        return "Error: Benchmark data missing 'Close' column"

    try:
        # Align dates via inner join
        aligned = pd.DataFrame({
            'stock_close': stock_data['Close'],
            'benchmark_close': benchmark_data['Close']
        }).dropna()

        if aligned.empty:
            return "Error: No overlapping dates between stock and benchmark data"

        # Check sufficient data for longest period
        # Allow some flexibility for trading days (250-252 trading days in a year)
        max_period = max(periods)
        # Require at least 98% of the period (e.g., 250 days for 252-day period)
        min_required = int(max_period * 0.98)
        if len(aligned) < min_required:
            return f"Error: Insufficient data. Need at least {min_required} days, have {len(aligned)}"

        # Calculate ROC for each period
        stock_rocs = []
        benchmark_rocs = []

        for period in periods:
            # ROC = (close / close.shift(period)) - 1
            # Use min of period and available data for flexibility with trading days
            actual_period = min(period, len(aligned) - 1)
            stock_roc = (aligned['stock_close'] / aligned['stock_close'].shift(actual_period)) - 1
            benchmark_roc = (aligned['benchmark_close'] / aligned['benchmark_close'].shift(actual_period)) - 1

            # Get the most recent ROC value
            stock_rocs.append(stock_roc.iloc[-1])
            benchmark_rocs.append(benchmark_roc.iloc[-1])

        # Check for NaN values
        if any(np.isnan(stock_rocs)) or any(np.isnan(benchmark_rocs)):
            return "Error: Unable to calculate ROC for all periods (NaN values)"

        # Apply IBD weighting: 0.4, 0.2, 0.2, 0.2
        weights = [0.4, 0.2, 0.2, 0.2]

        # Calculate weighted RS
        stock_rs = sum(roc * weight for roc, weight in zip(stock_rocs, weights))
        benchmark_rs = sum(roc * weight for roc, weight in zip(benchmark_rocs, weights))

        # Return relative strength (stock RS - benchmark RS)
        relative_strength = stock_rs - benchmark_rs

        return float(relative_strength)

    except Exception as e:
        return f"Error calculating relative strength: {str(e)}"


# ============================================================================
# Correlation Analysis
# ============================================================================

def calculate_rolling_correlation(
    stock_data: pd.DataFrame,
    benchmark_data: pd.DataFrame,
    window: int = 63
) -> Union[pd.Series, str]:
    """
    Calculate rolling correlation between stock and benchmark.

    Args:
        stock_data: DataFrame with 'Close' column
        benchmark_data: DataFrame with 'Close' column
        window: Rolling window size in days (default: 63 for ~3 months)

    Returns:
        pd.Series: Rolling correlation values (range: -1 to 1)
        str: Error message on failure

    Examples:
        >>> corr = calculate_rolling_correlation(stock_data, spy_data)
        >>> corr = calculate_rolling_correlation(stock_data, spy_data, window=20)
    """
    # Validate window
    if window < 2:
        return "Error: Window must be at least 2"

    # Validate inputs
    if stock_data.empty:
        return "Error: Stock data is empty"

    if benchmark_data.empty:
        return "Error: Benchmark data is empty"

    if 'Close' not in stock_data.columns:
        return "Error: Stock data missing 'Close' column"

    if 'Close' not in benchmark_data.columns:
        return "Error: Benchmark data missing 'Close' column"

    try:
        # Align dates via inner join
        aligned = pd.DataFrame({
            'stock_close': stock_data['Close'],
            'benchmark_close': benchmark_data['Close']
        }).dropna()

        if aligned.empty:
            return "Error: No overlapping dates between stock and benchmark data"

        # Calculate rolling correlation
        rolling_corr = aligned['stock_close'].rolling(window=window).corr(aligned['benchmark_close'])

        # Clip to [-1, 1] to handle floating point precision issues
        rolling_corr = rolling_corr.clip(-1.0, 1.0)

        return rolling_corr

    except Exception as e:
        return f"Error calculating rolling correlation: {str(e)}"


# ============================================================================
# Beta Calculation
# ============================================================================

def calculate_beta(
    stock_data: pd.DataFrame,
    benchmark_data: pd.DataFrame,
    window: int = 252
) -> Union[float, str]:
    """
    Calculate beta (systematic risk measure).

    Beta = Covariance(stock_returns, benchmark_returns) / Variance(benchmark_returns)

    Args:
        stock_data: DataFrame with 'Close' column
        benchmark_data: DataFrame with 'Close' column
        window: Number of days for calculation (default: 252 for ~1 year)

    Returns:
        float: Beta value
               Beta > 1: More volatile than benchmark
               Beta = 1: Same volatility as benchmark
               Beta < 1: Less volatile than benchmark
        str: Error message on failure

    Examples:
        >>> beta = calculate_beta(stock_data, spy_data)
        >>> beta = calculate_beta(stock_data, spy_data, window=126)
    """
    # Validate inputs
    if stock_data.empty:
        return "Error: Stock data is empty"

    if benchmark_data.empty:
        return "Error: Benchmark data is empty"

    if 'Close' not in stock_data.columns:
        return "Error: Stock data missing 'Close' column"

    if 'Close' not in benchmark_data.columns:
        return "Error: Benchmark data missing 'Close' column"

    try:
        # Align dates via inner join
        aligned = pd.DataFrame({
            'stock_close': stock_data['Close'],
            'benchmark_close': benchmark_data['Close']
        }).dropna()

        if aligned.empty:
            return "Error: No overlapping dates between stock and benchmark data"

        # Check sufficient data
        # For beta calculation, allow some flexibility for trading days
        min_required = int(window * 0.98)
        if len(aligned) < min_required:
            return f"Error: Insufficient data. Need at least {min_required} days, have {len(aligned)}"

        # Calculate returns
        stock_returns = aligned['stock_close'].pct_change()
        benchmark_returns = aligned['benchmark_close'].pct_change()

        # Take last window days
        stock_returns_window = stock_returns.tail(window)
        benchmark_returns_window = benchmark_returns.tail(window)

        # Remove NaN values
        valid_data = pd.DataFrame({
            'stock': stock_returns_window,
            'benchmark': benchmark_returns_window
        }).dropna()

        if valid_data.empty:
            return "Error: No valid returns data after removing NaN values"

        # Calculate covariance and variance
        covariance = valid_data['stock'].cov(valid_data['benchmark'])
        variance = valid_data['benchmark'].var()

        # Handle zero variance
        if variance == 0 or np.isnan(variance):
            return "Error: Benchmark has zero variance (no price movement)"

        # Calculate beta
        beta = covariance / variance

        # Check for NaN
        if np.isnan(beta):
            return "Error: Beta calculation resulted in NaN"

        return float(beta)

    except Exception as e:
        return f"Error calculating beta: {str(e)}"
