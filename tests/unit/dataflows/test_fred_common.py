"""
Test suite for FRED API Core Utilities (fred_common.py).

This module tests:
1. get_api_key() - API key retrieval from environment
2. FredRateLimitError exception class - Rate limit handling
3. FredInvalidSeriesError exception class - Invalid series handling
4. format_date_for_fred() - Date format conversion
5. _make_fred_request() - API request wrapper with retry logic
6. _get_cache_path() - Cache file path generation
7. _load_from_cache() - Cache data loading
8. _save_to_cache() - Cache data saving

Test Coverage:
- Unit tests for individual utility functions
- Edge cases (missing API key, invalid dates, network errors)
- Retry logic with exponential backoff
- Cache hit/miss scenarios
- Error handling and exception raising
"""

import pytest
import pandas as pd
import time
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
from datetime import datetime, date, timedelta
from typing import Optional

pytestmark = pytest.mark.unit


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_fred_api_key():
    """Mock FRED_API_KEY environment variable."""
    with patch.dict('os.environ', {'FRED_API_KEY': 'test_api_key_12345'}):
        yield 'test_api_key_12345'


@pytest.fixture
def mock_fred_api_key_missing():
    """Mock environment without FRED_API_KEY."""
    with patch.dict('os.environ', {}, clear=True):
        yield


@pytest.fixture
def sample_fred_dataframe():
    """Create a sample FRED data DataFrame."""
    return pd.DataFrame({
        'date': pd.date_range('2024-01-01', periods=5, freq='D'),
        'value': [5.33, 5.35, 5.37, 5.39, 5.40],
    })


@pytest.fixture
def mock_fredapi():
    """Mock fredapi.Fred class for testing."""
    with patch('tradingagents.dataflows.fred_common.Fred') as mock_fred_class:
        mock_fred_instance = MagicMock()
        mock_fred_class.return_value = mock_fred_instance
        yield mock_fred_instance


@pytest.fixture
def mock_cache_dir(tmp_path):
    """Create a temporary cache directory."""
    cache_dir = tmp_path / ".cache" / "fred"
    cache_dir.mkdir(parents=True, exist_ok=True)

    with patch('tradingagents.dataflows.fred_common.CACHE_DIR', cache_dir):
        yield cache_dir


# ============================================================================
# Test get_api_key()
# ============================================================================

class TestGetApiKey:
    """Test FRED API key retrieval from environment."""

    def test_get_api_key_success(self, mock_fred_api_key):
        """Test successful API key retrieval from environment."""
        from tradingagents.dataflows.fred_common import get_api_key

        api_key = get_api_key()

        assert api_key == 'test_api_key_12345'
        assert isinstance(api_key, str)
        assert len(api_key) > 0

    def test_get_api_key_missing_raises_value_error(self, mock_fred_api_key_missing):
        """Test that missing API key raises ValueError."""
        from tradingagents.dataflows.fred_common import get_api_key

        with pytest.raises(ValueError) as exc_info:
            get_api_key()

        assert "FRED_API_KEY" in str(exc_info.value)
        assert "environment variable" in str(exc_info.value).lower()

    def test_get_api_key_empty_string_raises_value_error(self):
        """Test that empty API key string raises ValueError."""
        with patch.dict('os.environ', {'FRED_API_KEY': ''}):
            from tradingagents.dataflows.fred_common import get_api_key

            with pytest.raises(ValueError) as exc_info:
                get_api_key()

            assert "FRED_API_KEY" in str(exc_info.value)

    def test_get_api_key_whitespace_only_raises_value_error(self):
        """Test that whitespace-only API key raises ValueError."""
        with patch.dict('os.environ', {'FRED_API_KEY': '   '}):
            from tradingagents.dataflows.fred_common import get_api_key

            with pytest.raises(ValueError) as exc_info:
                get_api_key()

            assert "FRED_API_KEY" in str(exc_info.value)


# ============================================================================
# Test Exception Classes
# ============================================================================

class TestFredRateLimitError:
    """Test FredRateLimitError exception class."""

    def test_exception_creation_with_message(self):
        """Test creating FredRateLimitError with just a message."""
        from tradingagents.dataflows.fred_common import FredRateLimitError

        error = FredRateLimitError("Rate limit exceeded")

        assert str(error) == "Rate limit exceeded"
        assert isinstance(error, Exception)

    def test_exception_creation_with_retry_after(self):
        """Test FredRateLimitError with retry_after parameter."""
        from tradingagents.dataflows.fred_common import FredRateLimitError

        error = FredRateLimitError("Rate limit exceeded", retry_after=60)

        assert str(error) == "Rate limit exceeded"
        assert error.retry_after == 60
        assert isinstance(error.retry_after, int)

    def test_exception_inheritance(self):
        """Test that FredRateLimitError inherits from Exception."""
        from tradingagents.dataflows.fred_common import FredRateLimitError

        error = FredRateLimitError("Test")
        assert isinstance(error, Exception)


class TestFredInvalidSeriesError:
    """Test FredInvalidSeriesError exception class."""

    def test_exception_creation_with_message(self):
        """Test creating FredInvalidSeriesError with message."""
        from tradingagents.dataflows.fred_common import FredInvalidSeriesError

        error = FredInvalidSeriesError("Invalid series: INVALID_ID")

        assert str(error) == "Invalid series: INVALID_ID"
        assert isinstance(error, Exception)

    def test_exception_creation_with_series_id(self):
        """Test FredInvalidSeriesError with series_id parameter."""
        from tradingagents.dataflows.fred_common import FredInvalidSeriesError

        error = FredInvalidSeriesError("Invalid series", series_id="INVALID_ID")

        assert error.series_id == "INVALID_ID"

    def test_exception_inheritance(self):
        """Test that FredInvalidSeriesError inherits from Exception."""
        from tradingagents.dataflows.fred_common import FredInvalidSeriesError

        error = FredInvalidSeriesError("Test")
        assert isinstance(error, Exception)


# ============================================================================
# Test format_date_for_fred()
# ============================================================================

class TestFormatDateForFred:
    """Test date format conversion for FRED API."""

    def test_format_datetime_object(self):
        """Test formatting datetime.datetime object."""
        from tradingagents.dataflows.fred_common import format_date_for_fred

        dt = datetime(2024, 1, 15, 10, 30, 45)
        result = format_date_for_fred(dt)

        assert result == "2024-01-15"
        assert isinstance(result, str)

    def test_format_date_object(self):
        """Test formatting datetime.date object."""
        from tradingagents.dataflows.fred_common import format_date_for_fred

        d = date(2024, 1, 15)
        result = format_date_for_fred(d)

        assert result == "2024-01-15"
        assert isinstance(result, str)

    def test_format_string_yyyy_mm_dd(self):
        """Test formatting string already in YYYY-MM-DD format."""
        from tradingagents.dataflows.fred_common import format_date_for_fred

        result = format_date_for_fred("2024-01-15")

        assert result == "2024-01-15"

    def test_format_string_mm_dd_yyyy(self):
        """Test formatting string in MM/DD/YYYY format."""
        from tradingagents.dataflows.fred_common import format_date_for_fred

        result = format_date_for_fred("01/15/2024")

        assert result == "2024-01-15"

    def test_format_string_dd_mm_yyyy(self):
        """Test formatting string in DD-MM-YYYY format."""
        from tradingagents.dataflows.fred_common import format_date_for_fred

        result = format_date_for_fred("15-01-2024")

        assert result == "2024-01-15"

    def test_format_timestamp(self):
        """Test formatting Unix timestamp."""
        from tradingagents.dataflows.fred_common import format_date_for_fred

        # Unix timestamp for 2024-01-15 00:00:00 UTC
        timestamp = 1705276800
        result = format_date_for_fred(timestamp)

        assert result == "2024-01-15"

    def test_format_none_returns_none(self):
        """Test that None input returns None."""
        from tradingagents.dataflows.fred_common import format_date_for_fred

        result = format_date_for_fred(None)

        assert result is None

    def test_format_invalid_string_raises_value_error(self):
        """Test that invalid date string raises ValueError."""
        from tradingagents.dataflows.fred_common import format_date_for_fred

        with pytest.raises(ValueError) as exc_info:
            format_date_for_fred("invalid-date")

        assert "date" in str(exc_info.value).lower()

    def test_format_future_date(self):
        """Test formatting future date."""
        from tradingagents.dataflows.fred_common import format_date_for_fred

        future = datetime.now() + timedelta(days=365)
        result = format_date_for_fred(future)

        assert isinstance(result, str)
        assert len(result) == 10  # YYYY-MM-DD format


# ============================================================================
# Test _make_fred_request()
# ============================================================================

class TestMakeFredRequest:
    """Test FRED API request wrapper with retry logic."""

    def test_successful_request_returns_dataframe(self, mock_fred_api_key, mock_fredapi, sample_fred_dataframe):
        """Test successful API request returns DataFrame."""
        from tradingagents.dataflows.fred_common import _make_fred_request

        mock_fredapi.get_series.return_value = sample_fred_dataframe

        result = _make_fred_request('FEDFUNDS')

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 5
        mock_fredapi.get_series.assert_called_once_with('FEDFUNDS', observation_start=None, observation_end=None)

    def test_request_with_date_range(self, mock_fred_api_key, mock_fredapi, sample_fred_dataframe):
        """Test API request with start and end dates."""
        from tradingagents.dataflows.fred_common import _make_fred_request

        mock_fredapi.get_series.return_value = sample_fred_dataframe

        result = _make_fred_request('FEDFUNDS', start_date='2024-01-01', end_date='2024-12-31')

        mock_fredapi.get_series.assert_called_once_with(
            'FEDFUNDS',
            observation_start='2024-01-01',
            observation_end='2024-12-31'
        )

    def test_rate_limit_429_raises_rate_limit_error(self, mock_fred_api_key, mock_fredapi):
        """Test that 429 response raises FredRateLimitError."""
        from tradingagents.dataflows.fred_common import _make_fred_request, FredRateLimitError

        # Mock HTTP 429 error
        error = Exception("429 Client Error: Too Many Requests")
        mock_fredapi.get_series.side_effect = error

        with pytest.raises(FredRateLimitError) as exc_info:
            _make_fred_request('FEDFUNDS')

        assert "rate limit" in str(exc_info.value).lower()

    def test_invalid_series_raises_invalid_series_error(self, mock_fred_api_key, mock_fredapi):
        """Test that invalid series ID raises FredInvalidSeriesError."""
        from tradingagents.dataflows.fred_common import _make_fred_request, FredInvalidSeriesError

        # Mock series not found error
        error = Exception("Series not found")
        mock_fredapi.get_series.side_effect = error

        with pytest.raises(FredInvalidSeriesError) as exc_info:
            _make_fred_request('INVALID_SERIES_ID')

        assert "INVALID_SERIES_ID" in str(exc_info.value)

    @patch('tradingagents.dataflows.fred_common.time.sleep')
    def test_network_timeout_retries_three_times(self, mock_sleep, mock_fred_api_key, mock_fredapi):
        """Test that network timeout triggers retry with exponential backoff."""
        from tradingagents.dataflows.fred_common import _make_fred_request

        # Mock timeout error
        timeout_error = Exception("Connection timeout")
        mock_fredapi.get_series.side_effect = timeout_error

        with pytest.raises(Exception) as exc_info:
            _make_fred_request('FEDFUNDS', max_retries=3)

        # Should retry 3 times (total 4 attempts including initial)
        assert mock_fredapi.get_series.call_count == 4

        # Should sleep with exponential backoff: 1s, 2s, 4s
        assert mock_sleep.call_count == 3
        sleep_calls = [call.args[0] for call in mock_sleep.call_args_list]
        assert sleep_calls == [1, 2, 4]

    @patch('tradingagents.dataflows.fred_common.time.sleep')
    def test_retry_succeeds_on_second_attempt(self, mock_sleep, mock_fred_api_key, mock_fredapi, sample_fred_dataframe):
        """Test successful retry after initial failure."""
        from tradingagents.dataflows.fred_common import _make_fred_request

        # First call fails, second succeeds
        mock_fredapi.get_series.side_effect = [
            Exception("Temporary error"),
            sample_fred_dataframe
        ]

        result = _make_fred_request('FEDFUNDS', max_retries=3)

        assert isinstance(result, pd.DataFrame)
        assert mock_fredapi.get_series.call_count == 2
        assert mock_sleep.call_count == 1

    def test_empty_dataframe_returns_empty(self, mock_fred_api_key, mock_fredapi):
        """Test that empty DataFrame is returned when no data available."""
        from tradingagents.dataflows.fred_common import _make_fred_request

        empty_df = pd.DataFrame()
        mock_fredapi.get_series.return_value = empty_df

        result = _make_fred_request('FEDFUNDS')

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0


# ============================================================================
# Test Cache Functions
# ============================================================================

class TestGetCachePath:
    """Test cache file path generation."""

    def test_get_cache_path_basic(self, mock_cache_dir):
        """Test basic cache path generation."""
        from tradingagents.dataflows.fred_common import _get_cache_path

        cache_path = _get_cache_path('FEDFUNDS')

        assert isinstance(cache_path, Path)
        assert cache_path.name == 'FEDFUNDS.parquet'
        assert cache_path.parent == mock_cache_dir

    def test_get_cache_path_with_dates(self, mock_cache_dir):
        """Test cache path includes date range in filename."""
        from tradingagents.dataflows.fred_common import _get_cache_path

        cache_path = _get_cache_path('FEDFUNDS', start_date='2024-01-01', end_date='2024-12-31')

        assert isinstance(cache_path, Path)
        assert 'FEDFUNDS' in cache_path.name
        assert '2024-01-01' in cache_path.name
        assert '2024-12-31' in cache_path.name
        assert cache_path.suffix == '.parquet'

    def test_get_cache_path_special_characters(self, mock_cache_dir):
        """Test cache path with series ID containing special characters."""
        from tradingagents.dataflows.fred_common import _get_cache_path

        cache_path = _get_cache_path('DGS10')

        assert isinstance(cache_path, Path)
        assert cache_path.name == 'DGS10.parquet'


class TestLoadFromCache:
    """Test loading data from cache."""

    def test_load_from_cache_hit(self, mock_cache_dir, sample_fred_dataframe):
        """Test successful cache load when file exists."""
        from tradingagents.dataflows.fred_common import _load_from_cache, _save_to_cache

        # Save to cache first
        cache_path = mock_cache_dir / 'FEDFUNDS.parquet'
        sample_fred_dataframe.to_parquet(cache_path)

        # Load from cache
        result = _load_from_cache('FEDFUNDS')

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 5
        assert list(result.columns) == list(sample_fred_dataframe.columns)

    def test_load_from_cache_miss_returns_none(self, mock_cache_dir):
        """Test cache miss returns None when file doesn't exist."""
        from tradingagents.dataflows.fred_common import _load_from_cache

        result = _load_from_cache('NONEXISTENT_SERIES')

        assert result is None

    def test_load_from_cache_expired_returns_none(self, mock_cache_dir, sample_fred_dataframe):
        """Test expired cache returns None."""
        from tradingagents.dataflows.fred_common import _load_from_cache

        # Save to cache
        cache_path = mock_cache_dir / 'FEDFUNDS.parquet'
        sample_fred_dataframe.to_parquet(cache_path)

        # Mock old modification time (25 hours ago)
        old_time = time.time() - (25 * 3600)
        os.utime(cache_path, (old_time, old_time))

        # Load from cache with 24hr TTL
        result = _load_from_cache('FEDFUNDS', cache_ttl_hours=24)

        assert result is None

    def test_load_from_cache_corrupted_returns_none(self, mock_cache_dir):
        """Test corrupted cache file returns None."""
        from tradingagents.dataflows.fred_common import _load_from_cache

        # Create corrupted cache file
        cache_path = mock_cache_dir / 'FEDFUNDS.parquet'
        cache_path.write_text("corrupted data")

        result = _load_from_cache('FEDFUNDS')

        assert result is None


class TestSaveToCache:
    """Test saving data to cache."""

    def test_save_to_cache_success(self, mock_cache_dir, sample_fred_dataframe):
        """Test successful cache save."""
        from tradingagents.dataflows.fred_common import _save_to_cache

        _save_to_cache('FEDFUNDS', sample_fred_dataframe)

        cache_path = mock_cache_dir / 'FEDFUNDS.parquet'
        assert cache_path.exists()

        # Verify data can be loaded
        loaded_df = pd.read_parquet(cache_path)
        assert len(loaded_df) == 5

    def test_save_to_cache_creates_directory(self, tmp_path, sample_fred_dataframe):
        """Test that cache directory is created if it doesn't exist."""
        from tradingagents.dataflows.fred_common import _save_to_cache

        new_cache_dir = tmp_path / "new_cache" / "fred"

        with patch('tradingagents.dataflows.fred_common.CACHE_DIR', new_cache_dir):
            _save_to_cache('FEDFUNDS', sample_fred_dataframe)

        assert new_cache_dir.exists()
        cache_path = new_cache_dir / 'FEDFUNDS.parquet'
        assert cache_path.exists()

    def test_save_to_cache_overwrites_existing(self, mock_cache_dir, sample_fred_dataframe):
        """Test that existing cache file is overwritten."""
        from tradingagents.dataflows.fred_common import _save_to_cache

        # Save initial data
        _save_to_cache('FEDFUNDS', sample_fred_dataframe)

        # Save new data
        new_df = pd.DataFrame({
            'date': pd.date_range('2024-06-01', periods=3, freq='D'),
            'value': [6.0, 6.1, 6.2],
        })
        _save_to_cache('FEDFUNDS', new_df)

        # Verify new data
        cache_path = mock_cache_dir / 'FEDFUNDS.parquet'
        loaded_df = pd.read_parquet(cache_path)
        assert len(loaded_df) == 3
        assert loaded_df['value'].iloc[0] == 6.0

    def test_save_empty_dataframe(self, mock_cache_dir):
        """Test saving empty DataFrame to cache."""
        from tradingagents.dataflows.fred_common import _save_to_cache

        empty_df = pd.DataFrame()
        _save_to_cache('FEDFUNDS', empty_df)

        cache_path = mock_cache_dir / 'FEDFUNDS.parquet'
        assert cache_path.exists()


# ============================================================================
# Integration Tests for Cache + Request
# ============================================================================

class TestCacheIntegration:
    """Test integration between cache and request functions."""

    def test_request_uses_cache_when_available(self, mock_cache_dir, mock_fred_api_key, mock_fredapi, sample_fred_dataframe):
        """Test that cached data is used instead of API call."""
        from tradingagents.dataflows.fred_common import _make_fred_request, _save_to_cache

        # Save to cache
        _save_to_cache('FEDFUNDS', sample_fred_dataframe)

        # Request should use cache (mock API should not be called)
        result = _make_fred_request('FEDFUNDS', use_cache=True)

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 5
        mock_fredapi.get_series.assert_not_called()

    def test_request_bypasses_cache_when_disabled(self, mock_cache_dir, mock_fred_api_key, mock_fredapi, sample_fred_dataframe):
        """Test that cache is bypassed when use_cache=False."""
        from tradingagents.dataflows.fred_common import _make_fred_request, _save_to_cache

        # Save to cache
        _save_to_cache('FEDFUNDS', sample_fred_dataframe)

        # Configure mock
        mock_fredapi.get_series.return_value = sample_fred_dataframe

        # Request should bypass cache
        result = _make_fred_request('FEDFUNDS', use_cache=False)

        mock_fredapi.get_series.assert_called_once()

    def test_request_saves_to_cache_after_api_call(self, mock_cache_dir, mock_fred_api_key, mock_fredapi, sample_fred_dataframe):
        """Test that API response is saved to cache."""
        from tradingagents.dataflows.fred_common import _make_fred_request

        mock_fredapi.get_series.return_value = sample_fred_dataframe

        # Make request
        result = _make_fred_request('FEDFUNDS', use_cache=True)

        # Verify cache file was created
        cache_path = mock_cache_dir / 'FEDFUNDS.parquet'
        assert cache_path.exists()

        # Verify cached data
        cached_df = pd.read_parquet(cache_path)
        assert len(cached_df) == 5
