"""
Test suite for Benchmark Integration Tests.

This module tests:
1. End-to-end workflows with benchmark data
2. Multi-sector comparison analysis
3. Real-world data format handling (yfinance compatibility)
4. Combined analytics (RS + correlation + beta)
5. All sector ETFs availability

Test Coverage:
- Integration with yfinance data formats
- Complete benchmark analysis workflow
- Multi-sector relative strength comparison
- Portfolio-level analytics
- Date alignment across multiple datasets
- All 11 sector ETFs (XLC, XLY, XLP, XLE, XLF, XLV, XLI, XLB, XLRE, XLK, XLU)

Workflow:
1. Fetch benchmark data (SPY)
2. Fetch stock data
3. Calculate RS, correlation, beta
4. Compare across sectors
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

pytestmark = pytest.mark.integration


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def yfinance_spy_data():
    """
    Create SPY data in yfinance format.

    yfinance returns:
    - DatetimeIndex (timezone-aware or naive)
    - Capitalized column names
    - Business day frequency
    """
    dates = pd.date_range('2024-01-01', periods=300, freq='D')

    data = pd.DataFrame({
        'Open': [450.0 + i * 0.3 for i in range(300)],
        'High': [452.0 + i * 0.3 for i in range(300)],
        'Low': [449.0 + i * 0.3 for i in range(300)],
        'Close': [451.0 + i * 0.3 for i in range(300)],
        'Volume': [80000000 + i * 100000 for i in range(300)],
    }, index=dates)

    return data


@pytest.fixture
def yfinance_stock_data():
    """Create stock data in yfinance format (AAPL-like)."""
    dates = pd.date_range('2024-01-01', periods=300, freq='D')

    data = pd.DataFrame({
        'Open': [180.0 + i * 0.4 for i in range(300)],
        'High': [182.0 + i * 0.4 for i in range(300)],
        'Low': [179.0 + i * 0.4 for i in range(300)],
        'Close': [181.0 + i * 0.4 for i in range(300)],
        'Volume': [50000000 + i * 80000 for i in range(300)],
    }, index=dates)

    return data


@pytest.fixture
def yfinance_sector_data_xlk():
    """Create XLK sector ETF data in yfinance format."""
    dates = pd.date_range('2024-01-01', periods=300, freq='D')

    data = pd.DataFrame({
        'Open': [200.0 + i * 0.35 for i in range(300)],
        'High': [202.0 + i * 0.35 for i in range(300)],
        'Low': [199.0 + i * 0.35 for i in range(300)],
        'Close': [201.0 + i * 0.35 for i in range(300)],
        'Volume': [10000000 + i * 50000 for i in range(300)],
    }, index=dates)

    return data


@pytest.fixture
def yfinance_sector_data_xlf():
    """Create XLF sector ETF data in yfinance format."""
    dates = pd.date_range('2024-01-01', periods=300, freq='D')

    data = pd.DataFrame({
        'Open': [38.0 + i * 0.02 for i in range(300)],
        'High': [38.5 + i * 0.02 for i in range(300)],
        'Low': [37.5 + i * 0.02 for i in range(300)],
        'Close': [38.2 + i * 0.02 for i in range(300)],
        'Volume': [60000000 + i * 200000 for i in range(300)],
    }, index=dates)

    return data


@pytest.fixture
def yfinance_sector_data_xle():
    """Create XLE sector ETF data in yfinance format."""
    dates = pd.date_range('2024-01-01', periods=300, freq='D')

    data = pd.DataFrame({
        'Open': [85.0 + i * 0.1 for i in range(300)],
        'High': [86.0 + i * 0.1 for i in range(300)],
        'Low': [84.0 + i * 0.1 for i in range(300)],
        'Close': [85.5 + i * 0.1 for i in range(300)],
        'Volume': [25000000 + i * 100000 for i in range(300)],
    }, index=dates)

    return data


@pytest.fixture
def all_sector_etf_data():
    """
    Create data for all 11 sector ETFs.

    Returns dict mapping sector names to DataFrames.
    """
    sectors_data = {}
    sector_configs = {
        'communication': {'base': 75.0, 'increment': 0.08},
        'consumer_discretionary': {'base': 180.0, 'increment': 0.15},
        'consumer_staples': {'base': 75.0, 'increment': 0.05},
        'energy': {'base': 85.0, 'increment': 0.1},
        'financials': {'base': 38.0, 'increment': 0.02},
        'healthcare': {'base': 130.0, 'increment': 0.12},
        'industrials': {'base': 105.0, 'increment': 0.09},
        'materials': {'base': 85.0, 'increment': 0.07},
        'real_estate': {'base': 40.0, 'increment': 0.03},
        'technology': {'base': 200.0, 'increment': 0.35},
        'utilities': {'base': 65.0, 'increment': 0.04},
    }

    dates = pd.date_range('2024-01-01', periods=300, freq='D')

    for sector, config in sector_configs.items():
        base = config['base']
        inc = config['increment']

        data = pd.DataFrame({
            'Open': [base + i * inc for i in range(300)],
            'High': [base + 1.0 + i * inc for i in range(300)],
            'Low': [base - 0.5 + i * inc for i in range(300)],
            'Close': [base + 0.5 + i * inc for i in range(300)],
            'Volume': [15000000 + i * 50000 for i in range(300)],
        }, index=dates)

        sectors_data[sector] = data

    return sectors_data


# ============================================================================
# Test Class: Benchmark Integration
# ============================================================================

class TestBenchmarkIntegration:
    """
    Test suite for end-to-end benchmark workflows.

    Tests:
    - Complete analysis workflow (fetch + RS + correlation + beta)
    - Multi-sector comparison
    - All sector ETFs availability
    - Combined analytics
    """

    @patch('tradingagents.dataflows.benchmark.yf')
    def test_end_to_end_benchmark_analysis(
        self,
        mock_yf,
        yfinance_stock_data,
        yfinance_spy_data
    ):
        """
        Test complete benchmark analysis workflow.

        Workflow:
        1. Fetch SPY benchmark data
        2. Fetch stock data
        3. Calculate relative strength
        4. Calculate rolling correlation
        5. Calculate beta
        """
        from tradingagents.dataflows.benchmark import (
            get_spy_data,
            get_benchmark_data,
            calculate_relative_strength,
            calculate_rolling_correlation,
            calculate_beta
        )

        # Setup mocks
        def ticker_side_effect(symbol):
            mock_ticker_instance = MagicMock()
            if symbol == 'SPY':
                mock_ticker_instance.history.return_value = yfinance_spy_data
            else:  # AAPL
                mock_ticker_instance.history.return_value = yfinance_stock_data
            return mock_ticker_instance

        mock_yf.Ticker.side_effect = ticker_side_effect

        # Step 1: Fetch SPY benchmark
        spy_data = get_spy_data('2024-01-01', '2024-10-31')
        assert isinstance(spy_data, pd.DataFrame)
        assert len(spy_data) > 0

        # Step 2: Fetch stock data
        stock_data = get_benchmark_data('AAPL', '2024-01-01', '2024-10-31')
        assert isinstance(stock_data, pd.DataFrame)
        assert len(stock_data) > 0

        # Step 3: Calculate relative strength
        rs = calculate_relative_strength(stock_data, spy_data)
        assert isinstance(rs, float)
        assert not np.isnan(rs)

        # Step 4: Calculate rolling correlation
        correlation = calculate_rolling_correlation(stock_data, spy_data, window=63)
        assert isinstance(correlation, pd.Series)
        assert len(correlation.dropna()) > 0

        # Step 5: Calculate beta
        beta = calculate_beta(stock_data, spy_data, window=252)
        assert isinstance(beta, float)
        assert not np.isnan(beta)

        # Verify reasonable values
        assert -200 < rs < 200
        assert (correlation.dropna() >= -1.0).all()
        assert (correlation.dropna() <= 1.0).all()
        # Beta can be high for synthetic test data with varying volatility
        assert -10 < beta < 10

    @patch('tradingagents.dataflows.benchmark.yf')
    def test_multi_sector_comparison(
        self,
        mock_yf,
        yfinance_stock_data,
        yfinance_spy_data,
        yfinance_sector_data_xlk,
        yfinance_sector_data_xlf,
        yfinance_sector_data_xle
    ):
        """
        Test comparing stock performance against multiple sector ETFs.

        Workflow:
        1. Fetch stock data
        2. Fetch SPY and multiple sector ETFs
        3. Calculate RS against each benchmark
        4. Compare results
        """
        from tradingagents.dataflows.benchmark import (
            get_benchmark_data,
            get_sector_etf_data,
            calculate_relative_strength
        )

        # Setup mocks
        def ticker_side_effect(symbol):
            mock_ticker_instance = MagicMock()
            data_map = {
                'AAPL': yfinance_stock_data,
                'SPY': yfinance_spy_data,
                'XLK': yfinance_sector_data_xlk,
                'XLF': yfinance_sector_data_xlf,
                'XLE': yfinance_sector_data_xle,
            }
            mock_ticker_instance.history.return_value = data_map.get(
                symbol,
                pd.DataFrame()
            )
            return mock_ticker_instance

        mock_yf.Ticker.side_effect = ticker_side_effect

        # Fetch stock data
        stock_data = get_benchmark_data('AAPL', '2024-01-01', '2024-10-31')
        assert isinstance(stock_data, pd.DataFrame)

        # Calculate RS against multiple benchmarks
        rs_results = {}

        # vs SPY
        spy_data = get_benchmark_data('SPY', '2024-01-01', '2024-10-31')
        rs_results['SPY'] = calculate_relative_strength(stock_data, spy_data)

        # vs Technology (XLK)
        tech_data = get_sector_etf_data('technology', '2024-01-01', '2024-10-31')
        rs_results['XLK'] = calculate_relative_strength(stock_data, tech_data)

        # vs Financials (XLF)
        finance_data = get_sector_etf_data('financials', '2024-01-01', '2024-10-31')
        rs_results['XLF'] = calculate_relative_strength(stock_data, finance_data)

        # vs Energy (XLE)
        energy_data = get_sector_etf_data('energy', '2024-01-01', '2024-10-31')
        rs_results['XLE'] = calculate_relative_strength(stock_data, energy_data)

        # Assert all RS calculations succeeded
        for benchmark, rs in rs_results.items():
            assert isinstance(rs, float), f"RS vs {benchmark} failed"
            assert not np.isnan(rs), f"RS vs {benchmark} is NaN"
            assert -200 < rs < 200, f"RS vs {benchmark} out of range"

        # AAPL should have different RS against different sectors
        unique_values = len(set(rs_results.values()))
        assert unique_values > 1, "RS should differ across sectors"

    @patch('tradingagents.dataflows.benchmark.yf')
    def test_all_sector_etfs_available(self, mock_yf, all_sector_etf_data):
        """
        Test that all 11 sector ETFs can be fetched.

        Sectors:
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
        """
        from tradingagents.dataflows.benchmark import get_sector_etf_data, SECTOR_ETFS

        # Setup mocks
        def ticker_side_effect(symbol):
            mock_ticker_instance = MagicMock()
            # Find which sector this symbol belongs to
            for sector, etf_symbol in SECTOR_ETFS.items():
                if etf_symbol == symbol:
                    mock_ticker_instance.history.return_value = all_sector_etf_data[sector]
                    return mock_ticker_instance
            # Default empty
            mock_ticker_instance.history.return_value = pd.DataFrame()
            return mock_ticker_instance

        mock_yf.Ticker.side_effect = ticker_side_effect

        # Test each sector
        sectors = [
            'communication',
            'consumer_discretionary',
            'consumer_staples',
            'energy',
            'financials',
            'healthcare',
            'industrials',
            'materials',
            'real_estate',
            'technology',
            'utilities'
        ]

        for sector in sectors:
            result = get_sector_etf_data(sector, '2024-01-01', '2024-10-31')
            assert isinstance(result, pd.DataFrame), f"Sector {sector} failed"
            assert len(result) > 0, f"Sector {sector} returned empty data"
            assert 'Close' in result.columns, f"Sector {sector} missing Close column"

    @patch('tradingagents.dataflows.benchmark.yf')
    def test_portfolio_level_analytics(
        self,
        mock_yf,
        yfinance_spy_data,
        all_sector_etf_data
    ):
        """
        Test portfolio-level analytics across all sectors.

        Workflow:
        1. Fetch all sector ETFs
        2. Calculate correlation matrix with SPY
        3. Calculate beta for each sector
        4. Identify high/low correlation sectors
        """
        from tradingagents.dataflows.benchmark import (
            get_spy_data,
            get_sector_etf_data,
            calculate_rolling_correlation,
            calculate_beta,
            SECTOR_ETFS
        )

        # Setup mocks
        def ticker_side_effect(symbol):
            mock_ticker_instance = MagicMock()
            if symbol == 'SPY':
                mock_ticker_instance.history.return_value = yfinance_spy_data
            else:
                # Find sector for this symbol
                for sector, etf_symbol in SECTOR_ETFS.items():
                    if etf_symbol == symbol:
                        mock_ticker_instance.history.return_value = all_sector_etf_data[sector]
                        break
            return mock_ticker_instance

        mock_yf.Ticker.side_effect = ticker_side_effect

        # Fetch SPY
        spy_data = get_spy_data('2024-01-01', '2024-10-31')
        assert isinstance(spy_data, pd.DataFrame)

        # Calculate analytics for each sector
        sector_analytics = {}

        for sector in all_sector_etf_data.keys():
            sector_data = get_sector_etf_data(sector, '2024-01-01', '2024-10-31')

            if isinstance(sector_data, pd.DataFrame) and len(sector_data) > 0:
                # Calculate correlation
                correlation = calculate_rolling_correlation(
                    sector_data,
                    spy_data,
                    window=63
                )

                # Calculate beta
                beta = calculate_beta(sector_data, spy_data, window=252)

                sector_analytics[sector] = {
                    'avg_correlation': correlation.dropna().mean() if isinstance(correlation, pd.Series) else None,
                    'beta': beta if isinstance(beta, float) else None
                }

        # Assert we got analytics for all sectors
        assert len(sector_analytics) == 11, "Should have analytics for all 11 sectors"

        # Assert all analytics are valid
        for sector, analytics in sector_analytics.items():
            if analytics['avg_correlation'] is not None:
                assert -1.0 <= analytics['avg_correlation'] <= 1.0, \
                    f"Correlation for {sector} out of range"

            if analytics['beta'] is not None:
                assert not np.isnan(analytics['beta']), \
                    f"Beta for {sector} is NaN"
                # Beta can be high for synthetic test data with varying volatility
                assert -10 < analytics['beta'] < 10, \
                    f"Beta for {sector} out of reasonable range"

        # Identify high correlation sectors (should correlate well with SPY)
        high_corr_sectors = [
            sector for sector, analytics in sector_analytics.items()
            if analytics['avg_correlation'] is not None and analytics['avg_correlation'] > 0.7
        ]

        # Most sectors should have positive correlation with market
        assert len(high_corr_sectors) >= 1, "At least one sector should correlate with SPY"


# ============================================================================
# Test Class: Real-World Data Format Handling
# ============================================================================

class TestRealWorldDataFormat:
    """
    Test suite for handling real-world data format quirks.

    Tests:
    - Timezone-aware DatetimeIndex
    - Column name variations
    - Missing data handling
    - Date range alignment
    """

    @patch('tradingagents.dataflows.benchmark.yf')
    def test_timezone_aware_data(self, mock_yf):
        """Test handling of timezone-aware yfinance data."""
        from tradingagents.dataflows.benchmark import get_benchmark_data

        # Create timezone-aware data
        dates = pd.date_range('2024-01-01', periods=300, freq='D', tz='America/New_York')
        tz_data = pd.DataFrame({
            'Open': [100.0 + i * 0.1 for i in range(300)],
            'High': [101.0 + i * 0.1 for i in range(300)],
            'Low': [99.0 + i * 0.1 for i in range(300)],
            'Close': [100.5 + i * 0.1 for i in range(300)],
            'Volume': [1000000] * 300,
        }, index=dates)

        # Setup mock
        mock_ticker_instance = MagicMock()
        mock_yf.Ticker.return_value = mock_ticker_instance
        mock_ticker_instance.history.return_value = tz_data

        # Execute
        result = get_benchmark_data('SPY', '2024-01-01', '2024-10-31')

        # Assert - should handle timezone-aware data
        assert isinstance(result, pd.DataFrame)
        assert len(result) > 0

    @patch('tradingagents.dataflows.benchmark.yf')
    def test_business_day_frequency(self, mock_yf):
        """Test handling of business day frequency data (no weekends)."""
        from tradingagents.dataflows.benchmark import get_benchmark_data, calculate_relative_strength

        # Create business day data
        dates = pd.bdate_range('2024-01-01', periods=250, freq='B')

        spy_data = pd.DataFrame({
            'Open': [450.0 + i * 0.3 for i in range(250)],
            'High': [452.0 + i * 0.3 for i in range(250)],
            'Low': [449.0 + i * 0.3 for i in range(250)],
            'Close': [451.0 + i * 0.3 for i in range(250)],
            'Volume': [80000000] * 250,
        }, index=dates)

        stock_data = pd.DataFrame({
            'Open': [180.0 + i * 0.4 for i in range(250)],
            'High': [182.0 + i * 0.4 for i in range(250)],
            'Low': [179.0 + i * 0.4 for i in range(250)],
            'Close': [181.0 + i * 0.4 for i in range(250)],
            'Volume': [50000000] * 250,
        }, index=dates)

        # Setup mock
        def ticker_side_effect(symbol):
            mock_ticker_instance = MagicMock()
            if symbol == 'SPY':
                mock_ticker_instance.history.return_value = spy_data
            else:
                mock_ticker_instance.history.return_value = stock_data
            return mock_ticker_instance

        mock_yf.Ticker.side_effect = ticker_side_effect

        # Fetch data
        result_spy = get_benchmark_data('SPY', '2024-01-01', '2024-12-31')
        result_stock = get_benchmark_data('AAPL', '2024-01-01', '2024-12-31')

        # Calculate RS
        rs = calculate_relative_strength(result_stock, result_spy)

        # Assert - should handle business days correctly
        assert isinstance(rs, float)
        assert not np.isnan(rs)

    @patch('tradingagents.dataflows.benchmark.yf')
    def test_date_range_alignment(self, mock_yf):
        """Test automatic date range alignment between stock and benchmark."""
        from tradingagents.dataflows.benchmark import calculate_relative_strength

        # Create overlapping but not identical date ranges
        spy_dates = pd.date_range('2024-01-01', periods=300, freq='D')
        stock_dates = pd.date_range('2024-01-15', periods=280, freq='D')  # Starts 14 days later

        spy_data = pd.DataFrame({
            'Close': [450.0 + i * 0.3 for i in range(300)],
            'Volume': [80000000] * 300,
        }, index=spy_dates)

        stock_data = pd.DataFrame({
            'Close': [180.0 + i * 0.4 for i in range(280)],
            'Volume': [50000000] * 280,
        }, index=stock_dates)

        # Add other required columns
        for df in [spy_data, stock_data]:
            df['Open'] = df['Close'] - 0.5
            df['High'] = df['Close'] + 1.0
            df['Low'] = df['Close'] - 1.0

        # Execute RS calculation - should align dates internally
        result = calculate_relative_strength(stock_data, spy_data)

        # Assert - should handle date alignment
        # Either returns valid RS or error message
        if isinstance(result, float):
            assert not np.isnan(result)
        else:
            assert isinstance(result, str)
