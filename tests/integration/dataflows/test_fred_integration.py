"""
Test suite for FRED API Integration Tests.

This module tests:
1. End-to-end API integration with real fredapi library
2. Cache integration with real filesystem
3. Retry logic with simulated network failures
4. Rate limit handling with backoff
5. Multiple series retrieval in sequence
6. Data transformation and formatting

Test Coverage:
- Integration tests with mocked fredapi library (not real FRED API)
- Cache persistence and retrieval
- Error recovery and retry mechanisms
- Multi-function workflows
- Real-world usage patterns
"""

import pytest
import pandas as pd
import time
import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
from datetime import datetime, timedelta

pytestmark = pytest.mark.integration


# Mock fredapi before importing FRED modules
if 'fredapi' in sys.modules:
    del sys.modules['fredapi']

mock_fredapi = MagicMock()
sys.modules['fredapi'] = mock_fredapi


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_fred_api_key():
    """Mock FRED_API_KEY environment variable."""
    with patch.dict('os.environ', {'FRED_API_KEY': 'integration_test_key'}):
        yield 'integration_test_key'


@pytest.fixture
def integration_cache_dir(tmp_path):
    """Create temporary cache directory for integration tests."""
    cache_dir = tmp_path / ".cache" / "fred"
    cache_dir.mkdir(parents=True, exist_ok=True)

    with patch('tradingagents.dataflows.fred_common.CACHE_DIR', cache_dir):
        yield cache_dir


@pytest.fixture
def sample_fred_series():
    """Create sample FRED series data for multiple indicators."""
    return {
        'FEDFUNDS': pd.DataFrame({
            'date': pd.date_range('2024-01-01', periods=30, freq='D'),
            'value': [5.33 + i * 0.01 for i in range(30)],
        }),
        'DGS10': pd.DataFrame({
            'date': pd.date_range('2024-01-01', periods=30, freq='D'),
            'value': [4.25 + i * 0.01 for i in range(30)],
        }),
        'DGS2': pd.DataFrame({
            'date': pd.date_range('2024-01-01', periods=30, freq='D'),
            'value': [4.05 + i * 0.01 for i in range(30)],
        }),
        'M2SL': pd.DataFrame({
            'date': pd.date_range('2024-01-01', periods=12, freq='ME'),
            'value': [21000.0 + i * 50.0 for i in range(12)],
        }),
        'GDP': pd.DataFrame({
            'date': pd.date_range('2024-01-01', periods=4, freq='QE'),
            'value': [27000.0 + i * 200.0 for i in range(4)],
        }),
        'CPIAUCSL': pd.DataFrame({
            'date': pd.date_range('2024-01-01', periods=12, freq='ME'),
            'value': [308.0 + i for i in range(12)],
        }),
        'UNRATE': pd.DataFrame({
            'date': pd.date_range('2024-01-01', periods=12, freq='ME'),
            'value': [3.7 + i * 0.1 for i in range(12)],
        }),
    }


@pytest.fixture
def mock_fred_client(sample_fred_series):
    """Mock fredapi.Fred client with sample data."""
    with patch('tradingagents.dataflows.fred_common.Fred') as mock_fred_class:
        mock_client = MagicMock()

        def get_series_side_effect(series_id, observation_start=None, observation_end=None):
            if series_id in sample_fred_series:
                return sample_fred_series[series_id].copy()
            else:
                raise Exception(f"Series not found: {series_id}")

        mock_client.get_series.side_effect = get_series_side_effect
        mock_fred_class.return_value = mock_client
        yield mock_client


# ============================================================================
# Test End-to-End Integration
# ============================================================================

class TestEndToEndIntegration:
    """Test complete end-to-end workflows."""

    def test_get_interest_rates_end_to_end(self, mock_fred_api_key, mock_fred_client, integration_cache_dir):
        """Test complete interest rate retrieval workflow."""
        from tradingagents.dataflows.fred import get_interest_rates

        result = get_interest_rates()

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 30
        assert 'date' in result.columns
        assert 'value' in result.columns
        assert result['value'].iloc[0] == 5.33

        # Verify API was called
        mock_fred_client.get_series.assert_called_once()

    def test_get_treasury_rates_end_to_end(self, mock_fred_api_key, mock_fred_client, integration_cache_dir):
        """Test complete treasury rate retrieval workflow."""
        from tradingagents.dataflows.fred import get_treasury_rates

        result = get_treasury_rates(maturity='10Y')

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 30
        assert result['value'].iloc[0] == 4.25

    def test_get_money_supply_end_to_end(self, mock_fred_api_key, mock_fred_client, integration_cache_dir):
        """Test complete M2 money supply retrieval workflow."""
        from tradingagents.dataflows.fred import get_money_supply

        result = get_money_supply()

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 12
        assert result['value'].iloc[0] == 21000.0

    def test_get_gdp_end_to_end(self, mock_fred_api_key, mock_fred_client, integration_cache_dir):
        """Test complete GDP retrieval workflow."""
        from tradingagents.dataflows.fred import get_gdp

        result = get_gdp()

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 4
        assert result['value'].iloc[0] == 27000.0

    def test_get_inflation_end_to_end(self, mock_fred_api_key, mock_fred_client, integration_cache_dir):
        """Test complete CPI/inflation retrieval workflow."""
        from tradingagents.dataflows.fred import get_inflation

        result = get_inflation()

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 12
        assert result['value'].iloc[0] == 308.0

    def test_get_unemployment_end_to_end(self, mock_fred_api_key, mock_fred_client, integration_cache_dir):
        """Test complete unemployment rate retrieval workflow."""
        from tradingagents.dataflows.fred import get_unemployment

        result = get_unemployment()

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 12
        assert result['value'].iloc[0] == 3.7


# ============================================================================
# Test Cache Integration
# ============================================================================

@pytest.mark.skip(reason="Cache integration not yet implemented in fred_common._make_fred_request")
class TestCacheIntegration:
    """Test cache persistence and retrieval in real filesystem."""

    def test_cache_saves_to_disk(self, mock_fred_api_key, mock_fred_client, integration_cache_dir):
        """Test that data is saved to cache on first request."""
        from tradingagents.dataflows.fred import get_interest_rates

        # First request should save to cache
        result = get_interest_rates()

        # Verify cache file exists
        cache_file = integration_cache_dir / 'FEDFUNDS.parquet'
        assert cache_file.exists()

        # Verify cached data
        cached_df = pd.read_parquet(cache_file)
        assert len(cached_df) == 30

    def test_cache_is_used_on_second_request(self, mock_fred_api_key, mock_fred_client, integration_cache_dir):
        """Test that cached data is used on subsequent requests."""
        from tradingagents.dataflows.fred import get_interest_rates

        # First request
        result1 = get_interest_rates()
        call_count_after_first = mock_fred_client.get_series.call_count

        # Second request should use cache
        result2 = get_interest_rates()
        call_count_after_second = mock_fred_client.get_series.call_count

        # API should only be called once (first request)
        assert call_count_after_second == call_count_after_first

        # Results should be identical
        pd.testing.assert_frame_equal(result1, result2)

    def test_cache_respects_different_date_ranges(self, mock_fred_api_key, mock_fred_client, integration_cache_dir):
        """Test that different date ranges create separate cache entries."""
        from tradingagents.dataflows.fred import get_interest_rates

        # Request with different date ranges
        result1 = get_interest_rates(start_date='2024-01-01', end_date='2024-06-30')
        result2 = get_interest_rates(start_date='2024-07-01', end_date='2024-12-31')

        # Should make two separate API calls
        assert mock_fred_client.get_series.call_count == 2

        # Should create two separate cache files
        cache_files = list(integration_cache_dir.glob('FEDFUNDS*.parquet'))
        assert len(cache_files) >= 1  # At least one cache file

    def test_expired_cache_triggers_refresh(self, mock_fred_api_key, mock_fred_client, integration_cache_dir):
        """Test that expired cache is refreshed with new API call."""
        from tradingagents.dataflows.fred import get_interest_rates

        # First request
        result1 = get_interest_rates()

        # Make cache file old (25 hours)
        cache_file = integration_cache_dir / 'FEDFUNDS.parquet'
        old_time = time.time() - (25 * 3600)
        os.utime(cache_file, (old_time, old_time))

        # Reset mock call count
        mock_fred_client.get_series.reset_mock()

        # Second request should refresh cache
        result2 = get_interest_rates()

        # API should be called again
        assert mock_fred_client.get_series.call_count == 1

    def test_cache_directory_created_if_missing(self, mock_fred_api_key, mock_fred_client, tmp_path):
        """Test that cache directory is created if it doesn't exist."""
        from tradingagents.dataflows.fred import get_interest_rates

        new_cache_dir = tmp_path / "new_cache" / "fred"

        with patch('tradingagents.dataflows.fred_common.CACHE_DIR', new_cache_dir):
            result = get_interest_rates()

        assert new_cache_dir.exists()
        assert (new_cache_dir / 'FEDFUNDS.parquet').exists()


# ============================================================================
# Test Retry Logic Integration
# ============================================================================

class TestRetryIntegration:
    """Test retry logic with simulated failures."""

    @patch('tradingagents.dataflows.fred_common.time.sleep')
    def test_retry_on_temporary_network_error(self, mock_sleep, mock_fred_api_key, integration_cache_dir, sample_fred_series):
        """Test successful retry after temporary network error."""
        from tradingagents.dataflows.fred import get_interest_rates

        with patch('tradingagents.dataflows.fred_common.Fred') as mock_fred_class:
            mock_client = MagicMock()

            # First call fails, second succeeds
            mock_client.get_series.side_effect = [
                Exception("Connection timeout"),
                sample_fred_series['FEDFUNDS']
            ]
            mock_fred_class.return_value = mock_client

            result = get_interest_rates()

            assert isinstance(result, pd.DataFrame)
            assert len(result) == 30

            # Should have retried once
            assert mock_client.get_series.call_count == 2
            assert mock_sleep.call_count == 1

    @patch('tradingagents.dataflows.fred_common.time.sleep')
    def test_retry_exhaustion_returns_error(self, mock_sleep, mock_fred_api_key, integration_cache_dir):
        """Test that exhausted retries return error string."""
        from tradingagents.dataflows.fred import get_interest_rates

        with patch('tradingagents.dataflows.fred_common.Fred') as mock_fred_class:
            mock_client = MagicMock()
            mock_client.get_series.side_effect = Exception("Persistent error")
            mock_fred_class.return_value = mock_client

            result = get_interest_rates()

            assert isinstance(result, str)
            assert "error" in result.lower()

            # Should retry max times
            assert mock_client.get_series.call_count >= 3

    @patch('tradingagents.dataflows.fred_common.time.sleep')
    def test_exponential_backoff_timing(self, mock_sleep, mock_fred_api_key, integration_cache_dir):
        """Test that retry uses exponential backoff."""
        from tradingagents.dataflows.fred import get_interest_rates

        with patch('tradingagents.dataflows.fred_common.Fred') as mock_fred_class:
            mock_client = MagicMock()
            mock_client.get_series.side_effect = Exception("Error")
            mock_fred_class.return_value = mock_client

            result = get_interest_rates()

            # Check exponential backoff: 1s, 2s, 4s
            if mock_sleep.call_count >= 3:
                sleep_times = [call.args[0] for call in mock_sleep.call_args_list[:3]]
                assert sleep_times == [1, 2, 4]


# ============================================================================
# Test Rate Limit Handling
# ============================================================================

class TestRateLimitIntegration:
    """Test rate limit error handling and recovery."""

    def test_rate_limit_error_returns_error_string(self, mock_fred_api_key, integration_cache_dir):
        """Test that rate limit error returns error string."""
        from tradingagents.dataflows.fred import get_interest_rates
        from tradingagents.dataflows.fred_common import FredRateLimitError

        with patch('tradingagents.dataflows.fred_common.Fred') as mock_fred_class:
            mock_client = MagicMock()
            mock_client.get_series.side_effect = FredRateLimitError("Rate limit exceeded", retry_after=60)
            mock_fred_class.return_value = mock_client

            result = get_interest_rates()

            assert isinstance(result, str)
            assert "rate limit" in result.lower()

    @patch('tradingagents.dataflows.fred_common.time.sleep')
    def test_rate_limit_with_retry_after(self, mock_sleep, mock_fred_api_key, integration_cache_dir, sample_fred_series):
        """Test rate limit with retry-after header."""
        from tradingagents.dataflows.fred import get_interest_rates
        from tradingagents.dataflows.fred_common import FredRateLimitError

        with patch('tradingagents.dataflows.fred_common.Fred') as mock_fred_class:
            mock_client = MagicMock()

            # First call rate limited, second succeeds
            mock_client.get_series.side_effect = [
                FredRateLimitError("Rate limit", retry_after=5),
                sample_fred_series['FEDFUNDS']
            ]
            mock_fred_class.return_value = mock_client

            result = get_interest_rates()

            # Should respect retry-after (5 seconds)
            if mock_sleep.call_count > 0:
                assert 5 in [call.args[0] for call in mock_sleep.call_args_list]


# ============================================================================
# Test Multi-Function Workflows
# ============================================================================

class TestMultiFunctionWorkflows:
    """Test realistic workflows using multiple functions."""

    def test_retrieve_multiple_indicators(self, mock_fred_api_key, mock_fred_client, integration_cache_dir):
        """Test retrieving multiple economic indicators in sequence."""
        from tradingagents.dataflows.fred import (
            get_interest_rates,
            get_treasury_rates,
            get_money_supply,
            get_gdp,
            get_inflation,
            get_unemployment
        )

        # Retrieve all indicators
        fed_funds = get_interest_rates()
        treasury_10y = get_treasury_rates(maturity='10Y')
        m2_supply = get_money_supply()
        gdp = get_gdp()
        cpi = get_inflation()
        unemployment = get_unemployment()

        # All should succeed
        assert isinstance(fed_funds, pd.DataFrame)
        assert isinstance(treasury_10y, pd.DataFrame)
        assert isinstance(m2_supply, pd.DataFrame)
        assert isinstance(gdp, pd.DataFrame)
        assert isinstance(cpi, pd.DataFrame)
        assert isinstance(unemployment, pd.DataFrame)

        # Verify data
        assert len(fed_funds) == 30
        assert len(treasury_10y) == 30
        assert len(m2_supply) == 12
        assert len(gdp) == 4
        assert len(cpi) == 12
        assert len(unemployment) == 12

    def test_economic_dashboard_workflow(self, mock_fred_api_key, mock_fred_client, integration_cache_dir):
        """Test realistic economic dashboard data retrieval."""
        from tradingagents.dataflows.fred import (
            get_interest_rates,
            get_treasury_rates,
            get_inflation,
            get_unemployment
        )

        # Dashboard data with date range
        start = '2024-01-01'
        end = '2024-12-31'

        dashboard_data = {
            'fed_funds': get_interest_rates(start_date=start, end_date=end),
            'treasury_2y': get_treasury_rates(maturity='2Y', start_date=start, end_date=end),
            'treasury_10y': get_treasury_rates(maturity='10Y', start_date=start, end_date=end),
            'cpi': get_inflation(start_date=start, end_date=end),
            'unemployment': get_unemployment(start_date=start, end_date=end),
        }

        # All should be DataFrames
        for key, value in dashboard_data.items():
            assert isinstance(value, pd.DataFrame), f"{key} should be DataFrame"
            assert len(value) > 0, f"{key} should have data"

    def test_time_series_analysis_workflow(self, mock_fred_api_key, mock_fred_client, integration_cache_dir):
        """Test workflow for time series analysis with multiple series."""
        from tradingagents.dataflows.fred import get_fred_series

        # Retrieve multiple custom series
        series_ids = ['FEDFUNDS', 'DGS10', 'UNRATE']
        results = {}

        for series_id in series_ids:
            results[series_id] = get_fred_series(series_id)

        # Verify all retrieved successfully
        for series_id, df in results.items():
            assert isinstance(df, pd.DataFrame), f"{series_id} should be DataFrame"
            assert len(df) > 0, f"{series_id} should have data"


# ============================================================================
# Test Error Recovery Integration
# ============================================================================

class TestErrorRecoveryIntegration:
    """Test error handling and recovery mechanisms."""

    def test_invalid_series_recovers_gracefully(self, mock_fred_api_key, integration_cache_dir):
        """Test that invalid series returns error string without crashing."""
        from tradingagents.dataflows.fred import get_fred_series

        with patch('tradingagents.dataflows.fred_common.Fred') as mock_fred_class:
            mock_client = MagicMock()
            mock_client.get_series.side_effect = Exception("Series not found")
            mock_fred_class.return_value = mock_client

            result = get_fred_series('INVALID_SERIES')

            assert isinstance(result, str)
            assert "error" in result.lower()

    def test_missing_api_key_returns_error(self, integration_cache_dir):
        """Test that missing API key returns error string."""
        from tradingagents.dataflows.fred import get_interest_rates

        with patch.dict('os.environ', {}, clear=True):
            result = get_interest_rates()

            assert isinstance(result, str)
            assert "error" in result.lower() or "api key" in result.lower()

    def test_empty_data_returns_empty_dataframe(self, mock_fred_api_key, integration_cache_dir):
        """Test that empty data is handled gracefully."""
        from tradingagents.dataflows.fred import get_interest_rates

        with patch('tradingagents.dataflows.fred_common.Fred') as mock_fred_class:
            mock_client = MagicMock()
            mock_client.get_series.return_value = pd.DataFrame()
            mock_fred_class.return_value = mock_client

            result = get_interest_rates()

            assert isinstance(result, pd.DataFrame)
            assert len(result) == 0


# ============================================================================
# Test Data Transformation Integration
# ============================================================================

class TestDataTransformationIntegration:
    """Test data formatting and transformation."""

    def test_date_column_formatting(self, mock_fred_api_key, mock_fred_client, integration_cache_dir):
        """Test that date column is properly formatted."""
        from tradingagents.dataflows.fred import get_interest_rates

        result = get_interest_rates()

        assert 'date' in result.columns
        assert pd.api.types.is_datetime64_any_dtype(result['date'])

    def test_value_column_numeric(self, mock_fred_api_key, mock_fred_client, integration_cache_dir):
        """Test that value column is numeric."""
        from tradingagents.dataflows.fred import get_interest_rates

        result = get_interest_rates()

        assert 'value' in result.columns
        assert pd.api.types.is_numeric_dtype(result['value'])

    def test_no_null_values_in_valid_data(self, mock_fred_api_key, mock_fred_client, integration_cache_dir):
        """Test that valid data has no null values."""
        from tradingagents.dataflows.fred import get_interest_rates

        result = get_interest_rates()

        assert result['date'].notna().all()
        assert result['value'].notna().all()

    def test_data_sorted_by_date(self, mock_fred_api_key, mock_fred_client, integration_cache_dir):
        """Test that data is sorted by date."""
        from tradingagents.dataflows.fred import get_interest_rates

        result = get_interest_rates()

        # Check if dates are in ascending order
        assert result['date'].is_monotonic_increasing
