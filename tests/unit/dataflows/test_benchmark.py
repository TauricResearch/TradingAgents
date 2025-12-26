"""
Test suite for Benchmark Data Functions (benchmark.py).

This module tests:
1. get_benchmark_data() - Generic benchmark data fetcher via yfinance
2. get_spy_data() - Convenience wrapper for SPY
3. get_sector_etf_data() - Sector ETF data (XLF, XLK, XLE, etc.)
4. calculate_relative_strength() - IBD-style RS calculation
5. calculate_rolling_correlation() - Rolling correlation between stock and benchmark
6. calculate_beta() - Beta calculation (Cov/Var)

Test Coverage:
- Unit tests for each function
- Valid data fetching (SPY, sector ETFs)
- Invalid inputs (bad symbols, dates, sectors)
- RS calculation with IBD formula: 0.4*ROC(63) + 0.2*ROC(126) + 0.2*ROC(189) + 0.2*ROC(252)
- Rolling correlation with configurable window
- Beta calculation with market variance
- Edge cases (empty data, insufficient data, missing columns, date misalignment)
- Zero returns handling
- Extreme values

SECTOR_ETFS Constants:
- communication: XLC
- consumer_discretionary: XLY
- consumer_staples: XLP
- energy: XLE
- financials: XLF
- healthcare: XLV
- industrials: XLI
- materials: XLB
- real_estate: XLRE
- technology: XLK
- utilities: XLU
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

pytestmark = pytest.mark.unit


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sample_spy_data():
    """
    Create 300 days of sample SPY OHLCV data.

    Returns a DataFrame with DatetimeIndex and columns: Open, High, Low, Close, Volume.
    Simulates realistic market data with upward trend.
    """
    dates = pd.date_range('2024-01-01', periods=300, freq='D')

    data = []
    base_price = 450.0

    for i, date in enumerate(dates):
        # Simulate gradual upward trend with some volatility
        trend = i * 0.3
        volatility = np.sin(i / 10) * 2

        open_price = base_price + trend + volatility
        high_price = open_price + 1.5 + abs(np.cos(i / 5))
        low_price = open_price - 1.5 - abs(np.sin(i / 7))
        close_price = open_price + 0.5 + np.sin(i / 3) * 0.5
        volume = 80000000 + i * 100000

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
def sample_stock_data():
    """
    Create 300 days of sample stock OHLCV data (AAPL-like pattern).

    Returns a DataFrame with DatetimeIndex and columns: Open, High, Low, Close, Volume.
    Simulates tech stock with higher volatility than SPY.
    """
    dates = pd.date_range('2024-01-01', periods=300, freq='D')

    data = []
    base_price = 180.0

    for i, date in enumerate(dates):
        # Higher volatility and stronger trend than SPY
        trend = i * 0.4
        volatility = np.sin(i / 8) * 3

        open_price = base_price + trend + volatility
        high_price = open_price + 2.0 + abs(np.cos(i / 4))
        low_price = open_price - 2.0 - abs(np.sin(i / 6))
        close_price = open_price + 0.8 + np.sin(i / 2.5) * 0.8
        volume = 50000000 + i * 80000

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
def sample_sector_data():
    """
    Create 300 days of sample XLK (technology sector) OHLCV data.

    Returns a DataFrame with DatetimeIndex and columns: Open, High, Low, Close, Volume.
    Similar to SPY but with sector-specific characteristics.
    """
    dates = pd.date_range('2024-01-01', periods=300, freq='D')

    data = []
    base_price = 200.0

    for i, date in enumerate(dates):
        # Tech sector - moderate trend with cyclical volatility
        trend = i * 0.35
        volatility = np.sin(i / 12) * 2.5

        open_price = base_price + trend + volatility
        high_price = open_price + 1.8 + abs(np.cos(i / 5.5))
        low_price = open_price - 1.8 - abs(np.sin(i / 6.5))
        close_price = open_price + 0.6 + np.sin(i / 3.5) * 0.6
        volume = 10000000 + i * 50000

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
def insufficient_data():
    """
    Create DataFrame with only 50 days (insufficient for full RS calculation).

    Insufficient for 252-day ROC calculation in relative strength.
    """
    dates = pd.date_range('2024-01-01', periods=50, freq='D')

    data = []
    base_price = 100.0

    for i, date in enumerate(dates):
        open_price = base_price + i * 0.2
        data.append({
            'Open': round(open_price, 2),
            'High': round(open_price + 1.0, 2),
            'Low': round(open_price - 0.5, 2),
            'Close': round(open_price + 0.3, 2),
            'Volume': 1000000
        })

    df = pd.DataFrame(data, index=dates)
    return df


@pytest.fixture
def missing_close_data():
    """Create DataFrame missing Close column."""
    dates = pd.date_range('2024-01-01', periods=100, freq='D')
    return pd.DataFrame({
        'Open': [100.0 + i * 0.1 for i in range(100)],
        'High': [102.0 + i * 0.1 for i in range(100)],
        'Low': [99.0 + i * 0.1 for i in range(100)],
        'Volume': [1000000] * 100,
    }, index=dates)


@pytest.fixture
def misaligned_dates_data(sample_spy_data):
    """
    Create stock data with different date range than SPY.

    50-day offset to test date alignment handling.
    """
    offset_dates = pd.date_range('2024-02-20', periods=250, freq='D')

    data = []
    base_price = 150.0

    for i, date in enumerate(offset_dates):
        open_price = base_price + i * 0.2
        data.append({
            'Open': round(open_price, 2),
            'High': round(open_price + 1.5, 2),
            'Low': round(open_price - 1.0, 2),
            'Close': round(open_price + 0.5, 2),
            'Volume': 2000000
        })

    return pd.DataFrame(data, index=offset_dates)


@pytest.fixture
def zero_returns_data():
    """Create DataFrame with zero returns (flat prices)."""
    dates = pd.date_range('2024-01-01', periods=300, freq='D')

    # All prices are constant (no returns)
    constant_price = 100.0

    data = []
    for date in dates:
        data.append({
            'Open': constant_price,
            'High': constant_price,
            'Low': constant_price,
            'Close': constant_price,
            'Volume': 1000000
        })

    df = pd.DataFrame(data, index=dates)
    return df


@pytest.fixture
def extreme_values_data():
    """Create DataFrame with extreme price values."""
    dates = pd.date_range('2024-01-01', periods=300, freq='D')

    data = []
    for i, date in enumerate(dates):
        # Extreme volatility: 50% daily moves
        if i % 2 == 0:
            close = 100.0 * (1.5 ** (i // 2))
        else:
            close = 100.0 * (1.5 ** (i // 2)) * 0.5

        data.append({
            'Open': close,
            'High': close * 1.1,
            'Low': close * 0.9,
            'Close': close,
            'Volume': 1000000
        })

    df = pd.DataFrame(data, index=dates)
    return df


# ============================================================================
# Test Class: Benchmark Data Fetching
# ============================================================================

class TestBenchmarkDataFetching:
    """
    Test suite for benchmark data fetching functions.

    Tests:
    - get_benchmark_data() with valid symbols
    - get_spy_data() convenience wrapper
    - get_sector_etf_data() with valid sectors
    - Invalid symbol handling
    - Invalid sector handling
    - Invalid date handling
    - Empty data handling
    """

    @patch('tradingagents.dataflows.benchmark.yf')
    def test_get_benchmark_data_valid_spy(self, mock_yf, sample_spy_data):
        """Test fetching valid SPY benchmark data."""
        from tradingagents.dataflows.benchmark import get_benchmark_data

        # Setup mock
        mock_ticker_instance = MagicMock()
        mock_yf.Ticker.return_value = mock_ticker_instance
        mock_ticker_instance.history.return_value = sample_spy_data

        # Execute
        result = get_benchmark_data('SPY', '2024-01-01', '2024-10-31')

        # Assert
        assert isinstance(result, pd.DataFrame)
        assert len(result) > 0
        assert 'Close' in result.columns
        assert 'Volume' in result.columns
        mock_yf.Ticker.assert_called_once_with('SPY')
        mock_ticker_instance.history.assert_called_once()

    @patch('tradingagents.dataflows.benchmark.yf')
    def test_get_benchmark_data_valid_sector_etf(self, mock_yf, sample_sector_data):
        """Test fetching valid sector ETF data (XLK)."""
        from tradingagents.dataflows.benchmark import get_benchmark_data

        # Setup mock
        mock_ticker_instance = MagicMock()
        mock_yf.Ticker.return_value = mock_ticker_instance
        mock_ticker_instance.history.return_value = sample_sector_data

        # Execute
        result = get_benchmark_data('XLK', '2024-01-01', '2024-10-31')

        # Assert
        assert isinstance(result, pd.DataFrame)
        assert len(result) > 0
        assert 'Close' in result.columns
        mock_yf.Ticker.assert_called_once_with('XLK')

    @patch('tradingagents.dataflows.benchmark.yf')
    def test_get_benchmark_data_invalid_symbol(self, mock_yf):
        """Test handling of invalid ticker symbol."""
        from tradingagents.dataflows.benchmark import get_benchmark_data

        # Setup mock to raise exception
        mock_ticker_instance = MagicMock()
        mock_yf.Ticker.return_value = mock_ticker_instance
        mock_ticker_instance.history.side_effect = Exception("Invalid ticker")

        # Execute
        result = get_benchmark_data('INVALID_SYMBOL', '2024-01-01', '2024-10-31')

        # Assert - should return error string
        assert isinstance(result, str)
        assert 'error' in result.lower() or 'invalid' in result.lower()

    @patch('tradingagents.dataflows.benchmark.yf')
    def test_get_benchmark_data_empty_data(self, mock_yf):
        """Test handling when yfinance returns empty DataFrame."""
        from tradingagents.dataflows.benchmark import get_benchmark_data

        # Setup mock to return empty DataFrame
        mock_ticker_instance = MagicMock()
        mock_yf.Ticker.return_value = mock_ticker_instance
        mock_ticker_instance.history.return_value = pd.DataFrame()

        # Execute
        result = get_benchmark_data('SPY', '2024-01-01', '2024-01-02')

        # Assert
        assert isinstance(result, str)
        assert 'no data' in result.lower() or 'empty' in result.lower()

    @patch('tradingagents.dataflows.benchmark.yf')
    def test_get_spy_data(self, mock_yf, sample_spy_data):
        """Test get_spy_data() convenience wrapper."""
        from tradingagents.dataflows.benchmark import get_spy_data

        # Setup mock
        mock_ticker_instance = MagicMock()
        mock_yf.Ticker.return_value = mock_ticker_instance
        mock_ticker_instance.history.return_value = sample_spy_data

        # Execute
        result = get_spy_data('2024-01-01', '2024-10-31')

        # Assert
        assert isinstance(result, pd.DataFrame)
        assert len(result) > 0
        mock_yf.Ticker.assert_called_once_with('SPY')

    @patch('tradingagents.dataflows.benchmark.yf')
    def test_get_sector_etf_data_valid(self, mock_yf, sample_sector_data):
        """Test get_sector_etf_data() with valid sector."""
        from tradingagents.dataflows.benchmark import get_sector_etf_data

        # Setup mock
        mock_ticker_instance = MagicMock()
        mock_yf.Ticker.return_value = mock_ticker_instance
        mock_ticker_instance.history.return_value = sample_sector_data

        # Execute
        result = get_sector_etf_data('technology', '2024-01-01', '2024-10-31')

        # Assert
        assert isinstance(result, pd.DataFrame)
        assert len(result) > 0
        mock_yf.Ticker.assert_called_once_with('XLK')

    def test_get_sector_etf_data_invalid_sector(self):
        """Test get_sector_etf_data() with invalid sector name."""
        from tradingagents.dataflows.benchmark import get_sector_etf_data

        # Execute
        result = get_sector_etf_data('invalid_sector', '2024-01-01', '2024-10-31')

        # Assert
        assert isinstance(result, str)
        assert 'invalid' in result.lower() or 'unknown' in result.lower()

    @patch('tradingagents.dataflows.benchmark.yf')
    def test_get_benchmark_data_invalid_dates(self, mock_yf):
        """Test handling of invalid date format."""
        from tradingagents.dataflows.benchmark import get_benchmark_data

        # Setup mock to raise exception on invalid dates
        mock_ticker_instance = MagicMock()
        mock_yf.Ticker.return_value = mock_ticker_instance
        mock_ticker_instance.history.side_effect = ValueError("Invalid date format")

        # Execute
        result = get_benchmark_data('SPY', 'invalid-date', '2024-10-31')

        # Assert
        assert isinstance(result, str)
        assert 'error' in result.lower() or 'invalid' in result.lower()


# ============================================================================
# Test Class: Relative Strength Calculation
# ============================================================================

class TestRelativeStrength:
    """
    Test suite for IBD-style relative strength calculation.

    Tests:
    - RS calculation with IBD formula: 0.4*ROC(63) + 0.2*ROC(126) + 0.2*ROC(189) + 0.2*ROC(252)
    - Insufficient data handling (< 252 days)
    - Missing Close column
    - Date misalignment between stock and benchmark
    - Zero returns (flat prices)

    IBD Relative Strength:
    - 40% weight on 63-day (3-month) ROC
    - 20% weight on 126-day (6-month) ROC
    - 20% weight on 189-day (9-month) ROC
    - 20% weight on 252-day (12-month) ROC
    """

    def test_calculate_relative_strength_valid(self, sample_stock_data, sample_spy_data):
        """Test RS calculation with valid data."""
        from tradingagents.dataflows.benchmark import calculate_relative_strength

        # Execute
        result = calculate_relative_strength(sample_stock_data, sample_spy_data)

        # Assert
        assert isinstance(result, float)
        assert not np.isnan(result)
        assert not np.isinf(result)
        # RS should be reasonable (typically between -100 and 100 for normal stocks)
        assert -200 < result < 200

    def test_calculate_relative_strength_custom_periods(self, sample_stock_data, sample_spy_data):
        """Test RS calculation with custom periods."""
        from tradingagents.dataflows.benchmark import calculate_relative_strength

        # Execute with shorter periods (all data has 300 days)
        result = calculate_relative_strength(
            sample_stock_data,
            sample_spy_data,
            periods=[20, 60, 120, 180]
        )

        # Assert
        assert isinstance(result, float)
        assert not np.isnan(result)
        assert -200 < result < 200

    def test_calculate_relative_strength_insufficient_data(self, insufficient_data, sample_spy_data):
        """Test RS calculation with insufficient data (< 252 days)."""
        from tradingagents.dataflows.benchmark import calculate_relative_strength

        # Execute - only 50 days, need 252 for default periods
        result = calculate_relative_strength(insufficient_data, sample_spy_data)

        # Assert - should return error string
        assert isinstance(result, str)
        assert 'insufficient' in result.lower() or 'not enough' in result.lower()

    def test_calculate_relative_strength_missing_close(self, missing_close_data, sample_spy_data):
        """Test RS calculation with missing Close column."""
        from tradingagents.dataflows.benchmark import calculate_relative_strength

        # Execute
        result = calculate_relative_strength(missing_close_data, sample_spy_data)

        # Assert
        assert isinstance(result, str)
        assert 'close' in result.lower() or 'missing' in result.lower()

    def test_calculate_relative_strength_date_misalignment(self, misaligned_dates_data, sample_spy_data):
        """Test RS calculation with misaligned date ranges."""
        from tradingagents.dataflows.benchmark import calculate_relative_strength

        # Execute - stock data starts 50 days later than SPY
        result = calculate_relative_strength(misaligned_dates_data, sample_spy_data)

        # Assert - function should handle alignment or return error
        # Either valid RS (if aligned) or error message
        if isinstance(result, str):
            assert 'align' in result.lower() or 'date' in result.lower() or 'insufficient' in result.lower()
        else:
            assert isinstance(result, float)
            assert not np.isnan(result)

    def test_calculate_relative_strength_zero_returns(self, zero_returns_data, sample_spy_data):
        """Test RS calculation with zero returns (flat prices)."""
        from tradingagents.dataflows.benchmark import calculate_relative_strength

        # Execute
        result = calculate_relative_strength(zero_returns_data, sample_spy_data)

        # Assert - should handle zero returns gracefully
        # RS should be negative since stock has 0 returns while benchmark moves
        if isinstance(result, float):
            assert not np.isnan(result)
            assert result < 0  # Stock underperforming benchmark
        else:
            # Or return error for zero variance
            assert isinstance(result, str)


# ============================================================================
# Test Class: Correlation Analytics
# ============================================================================

class TestCorrelationAnalytics:
    """
    Test suite for correlation and beta calculations.

    Tests:
    - calculate_rolling_correlation() with various windows
    - calculate_beta() calculation
    - Window validation (must be >= 2)
    - Insufficient data for window size
    """

    def test_calculate_rolling_correlation_valid(self, sample_stock_data, sample_spy_data):
        """Test rolling correlation calculation with default window (63 days)."""
        from tradingagents.dataflows.benchmark import calculate_rolling_correlation

        # Execute
        result = calculate_rolling_correlation(sample_stock_data, sample_spy_data)

        # Assert
        assert isinstance(result, pd.Series)
        assert len(result) > 0
        # Correlation values should be between -1 and 1
        assert (result.dropna() >= -1.0).all()
        assert (result.dropna() <= 1.0).all()

    def test_calculate_rolling_correlation_custom_window(self, sample_stock_data, sample_spy_data):
        """Test rolling correlation with custom window size."""
        from tradingagents.dataflows.benchmark import calculate_rolling_correlation

        # Execute with 20-day window
        result = calculate_rolling_correlation(sample_stock_data, sample_spy_data, window=20)

        # Assert
        assert isinstance(result, pd.Series)
        assert len(result) > 0
        assert (result.dropna() >= -1.0).all()
        assert (result.dropna() <= 1.0).all()

    def test_calculate_rolling_correlation_invalid_window(self, sample_stock_data, sample_spy_data):
        """Test rolling correlation with invalid window (< 2)."""
        from tradingagents.dataflows.benchmark import calculate_rolling_correlation

        # Execute with window=1
        result = calculate_rolling_correlation(sample_stock_data, sample_spy_data, window=1)

        # Assert - should return error
        assert isinstance(result, str)
        assert 'window' in result.lower() or 'invalid' in result.lower()

    def test_calculate_rolling_correlation_insufficient_data(self, insufficient_data, sample_spy_data):
        """Test rolling correlation with insufficient data for window."""
        from tradingagents.dataflows.benchmark import calculate_rolling_correlation

        # Execute - only 50 days but default window is 63
        result = calculate_rolling_correlation(insufficient_data, sample_spy_data)

        # Assert - should return error or empty series
        if isinstance(result, str):
            assert 'insufficient' in result.lower() or 'not enough' in result.lower()
        elif isinstance(result, pd.Series):
            # May return series with all NaN values
            assert result.dropna().empty or len(result.dropna()) < 10

    def test_calculate_beta_valid(self, sample_stock_data, sample_spy_data):
        """Test beta calculation with default window (252 days)."""
        from tradingagents.dataflows.benchmark import calculate_beta

        # Execute
        result = calculate_beta(sample_stock_data, sample_spy_data)

        # Assert
        assert isinstance(result, float)
        assert not np.isnan(result)
        assert not np.isinf(result)
        # Beta typically ranges from -2 to 3 for normal stocks
        assert -5 < result < 5

    def test_calculate_beta_custom_window(self, sample_stock_data, sample_spy_data):
        """Test beta calculation with custom window."""
        from tradingagents.dataflows.benchmark import calculate_beta

        # Execute with 126-day window
        result = calculate_beta(sample_stock_data, sample_spy_data, window=126)

        # Assert
        assert isinstance(result, float)
        assert not np.isnan(result)
        assert -5 < result < 5

    def test_calculate_beta_insufficient_data(self, insufficient_data, sample_spy_data):
        """Test beta calculation with insufficient data."""
        from tradingagents.dataflows.benchmark import calculate_beta

        # Execute - only 50 days but default window is 252
        result = calculate_beta(insufficient_data, sample_spy_data)

        # Assert
        assert isinstance(result, str)
        assert 'insufficient' in result.lower() or 'not enough' in result.lower()

    def test_calculate_beta_zero_variance(self, zero_returns_data, sample_spy_data):
        """Test beta calculation when stock has zero variance."""
        from tradingagents.dataflows.benchmark import calculate_beta

        # Execute
        result = calculate_beta(zero_returns_data, sample_spy_data)

        # Assert - should handle zero variance
        if isinstance(result, float):
            assert result == 0.0 or np.isnan(result)
        else:
            assert isinstance(result, str)


# ============================================================================
# Test Class: Edge Cases
# ============================================================================

class TestEdgeCases:
    """
    Test suite for edge cases and boundary conditions.

    Tests:
    - Empty DataFrames
    - Single day data
    - Extreme values
    - Date index validation
    """

    def test_calculate_relative_strength_empty_stock(self, empty_dataframe, sample_spy_data):
        """Test RS calculation with empty stock DataFrame."""
        from tradingagents.dataflows.benchmark import calculate_relative_strength

        # Execute
        result = calculate_relative_strength(empty_dataframe, sample_spy_data)

        # Assert
        assert isinstance(result, str)
        assert 'empty' in result.lower() or 'no data' in result.lower()

    def test_calculate_relative_strength_empty_benchmark(self, sample_stock_data, empty_dataframe):
        """Test RS calculation with empty benchmark DataFrame."""
        from tradingagents.dataflows.benchmark import calculate_relative_strength

        # Execute
        result = calculate_relative_strength(sample_stock_data, empty_dataframe)

        # Assert
        assert isinstance(result, str)
        assert 'empty' in result.lower() or 'no data' in result.lower()

    def test_calculate_rolling_correlation_single_day(self, sample_spy_data):
        """Test rolling correlation with single day data."""
        from tradingagents.dataflows.benchmark import calculate_rolling_correlation

        # Create single day data
        single_day = sample_spy_data.iloc[[0]]

        # Execute
        result = calculate_rolling_correlation(single_day, sample_spy_data)

        # Assert
        assert isinstance(result, str) or (isinstance(result, pd.Series) and result.dropna().empty)

    def test_calculate_beta_extreme_values(self, extreme_values_data, sample_spy_data):
        """Test beta calculation with extreme price movements."""
        from tradingagents.dataflows.benchmark import calculate_beta

        # Execute
        result = calculate_beta(extreme_values_data, sample_spy_data)

        # Assert - should handle extreme values
        if isinstance(result, float):
            assert not np.isnan(result)
            # Beta can be very high for extreme volatility
            assert -100 < result < 100
        else:
            # Or return error for numerical issues
            assert isinstance(result, str)

    def test_get_benchmark_data_no_datetime_index(self):
        """Test that fetched data has proper DatetimeIndex."""
        # This tests that the implementation converts yfinance data correctly
        # Will be tested in integration tests with actual yfinance calls
        pass

    def test_sector_etf_constants_coverage(self):
        """Test that all expected sector ETFs are defined in SECTOR_ETFS constant."""
        from tradingagents.dataflows.benchmark import SECTOR_ETFS

        # Expected sectors
        expected_sectors = [
            'communication', 'consumer_discretionary', 'consumer_staples',
            'energy', 'financials', 'healthcare', 'industrials',
            'materials', 'real_estate', 'technology', 'utilities'
        ]

        # Assert all sectors exist
        for sector in expected_sectors:
            assert sector in SECTOR_ETFS, f"Missing sector: {sector}"

        # Assert expected symbols
        assert SECTOR_ETFS['technology'] == 'XLK'
        assert SECTOR_ETFS['financials'] == 'XLF'
        assert SECTOR_ETFS['energy'] == 'XLE'
        assert SECTOR_ETFS['healthcare'] == 'XLV'
        assert SECTOR_ETFS['industrials'] == 'XLI'
        assert SECTOR_ETFS['materials'] == 'XLB'
        assert SECTOR_ETFS['consumer_discretionary'] == 'XLY'
        assert SECTOR_ETFS['consumer_staples'] == 'XLP'
        assert SECTOR_ETFS['real_estate'] == 'XLRE'
        assert SECTOR_ETFS['utilities'] == 'XLU'
        assert SECTOR_ETFS['communication'] == 'XLC'
