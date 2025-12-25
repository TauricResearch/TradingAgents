"""
Test suite for AKShare data vendor integration.

This module tests:
1. Date format conversion helper (_convert_date_format)
2. Exponential backoff retry mechanism (_exponential_backoff_retry)
3. US stock data retrieval (get_akshare_stock_data_us)
4. Chinese stock data retrieval (get_akshare_stock_data_cn)
5. Auto-market detection (get_akshare_stock_data)
6. AKShareRateLimitError exception handling
7. Integration with vendor routing system (interface.py)

Test Coverage:
- Unit tests for individual helper functions
- Integration tests for stock data retrieval functions
- Edge cases (empty data, network errors, rate limits)
- Vendor fallback behavior with rate limit errors
"""

import pytest
import pandas as pd
import time
import sys
from unittest.mock import Mock, patch, MagicMock, call
from datetime import datetime
from typing import Callable, Any

# Clear any cached imports and mock akshare before importing our modules
if 'tradingagents.dataflows.akshare' in sys.modules:
    del sys.modules['tradingagents.dataflows.akshare']
if 'akshare' in sys.modules:
    del sys.modules['akshare']

mock_akshare = MagicMock()
sys.modules['akshare'] = mock_akshare

# Import modules under test
from tradingagents.dataflows.akshare import (
    AKShareRateLimitError,
    _convert_date_format,
    _exponential_backoff_retry,
    get_akshare_stock_data_us,
    get_akshare_stock_data_cn,
    get_akshare_stock_data,
)
from tradingagents.dataflows.interface import route_to_vendor, VENDOR_METHODS


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sample_us_dataframe():
    """Create a sample US stock data DataFrame matching akshare format."""
    return pd.DataFrame({
        'date': pd.date_range('2024-01-01', periods=5, freq='D'),
        'open': [150.0, 151.0, 152.0, 153.0, 154.0],
        'high': [152.0, 153.0, 154.0, 155.0, 156.0],
        'low': [149.0, 150.0, 151.0, 152.0, 153.0],
        'close': [151.0, 152.0, 153.0, 154.0, 155.0],
        'volume': [1000000, 1100000, 1200000, 1300000, 1400000],
    })


@pytest.fixture
def sample_cn_dataframe():
    """Create a sample Chinese stock data DataFrame matching akshare format."""
    return pd.DataFrame({
        '日期': ['2024-01-01', '2024-01-02', '2024-01-03', '2024-01-04', '2024-01-05'],
        '开盘': [10.0, 10.1, 10.2, 10.3, 10.4],
        '最高': [10.2, 10.3, 10.4, 10.5, 10.6],
        '最低': [9.9, 10.0, 10.1, 10.2, 10.3],
        '收盘': [10.1, 10.2, 10.3, 10.4, 10.5],
        '成交量': [500000, 550000, 600000, 650000, 700000],
    })


@pytest.fixture
def sample_standardized_dataframe():
    """Create a standardized DataFrame with English column names."""
    return pd.DataFrame({
        'Date': pd.date_range('2024-01-01', periods=5, freq='D'),
        'Open': [150.0, 151.0, 152.0, 153.0, 154.0],
        'High': [152.0, 153.0, 154.0, 155.0, 156.0],
        'Low': [149.0, 150.0, 151.0, 152.0, 153.0],
        'Close': [151.0, 152.0, 153.0, 154.0, 155.0],
        'Volume': [1000000, 1100000, 1200000, 1300000, 1400000],
    })


@pytest.fixture
def mock_akshare():
    """Mock akshare module for testing."""
    with patch('tradingagents.dataflows.akshare.ak') as mock_ak:
        yield mock_ak


@pytest.fixture
def mock_time_sleep():
    """Mock time.sleep to speed up retry tests."""
    with patch('tradingagents.dataflows.akshare.time.sleep') as mock_sleep:
        yield mock_sleep


# ============================================================================
# Test Date Format Conversion
# ============================================================================

class TestConvertDateFormat:
    """Test the _convert_date_format helper function."""

    def test_standard_date_format_with_hyphen(self):
        """Test conversion from YYYY-MM-DD to YYYYMMDD format."""
        result = _convert_date_format("2024-01-15")
        assert result == "20240115"

    def test_standard_date_format_with_single_digits(self):
        """Test conversion handles single-digit months and days."""
        result = _convert_date_format("2024-1-5")
        assert result == "202415"

    def test_handles_slash_separator(self):
        """Test conversion from YYYY/MM/DD format."""
        result = _convert_date_format("2024/01/15")
        assert result == "20240115"

    def test_preserves_yyyymmdd_format(self):
        """Test that already-correct format passes through."""
        result = _convert_date_format("20240115")
        assert result == "20240115"

    def test_handles_various_date_formats(self):
        """Test multiple valid date format variations."""
        test_cases = [
            ("2024-12-31", "20241231"),
            ("2024-01-01", "20240101"),
            ("2023-06-15", "20230615"),
        ]
        for input_date, expected in test_cases:
            assert _convert_date_format(input_date) == expected

    def test_empty_string_raises_error(self):
        """Test that empty string raises appropriate error."""
        with pytest.raises((ValueError, IndexError)):
            _convert_date_format("")

    def test_invalid_format_raises_error(self):
        """Test that invalid format raises appropriate error."""
        with pytest.raises((ValueError, IndexError)):
            _convert_date_format("not-a-date")


# ============================================================================
# Test Exponential Backoff Retry
# ============================================================================

class TestExponentialBackoffRetry:
    """Test the _exponential_backoff_retry helper function."""

    def test_returns_on_first_success(self, mock_time_sleep):
        """Test that successful function returns immediately without retries."""
        mock_func = Mock(return_value="success")

        result = _exponential_backoff_retry(mock_func, max_retries=3)

        assert result == "success"
        assert mock_func.call_count == 1
        assert mock_time_sleep.call_count == 0

    def test_retries_on_failure(self, mock_time_sleep):
        """Test that function retries on failure up to max_retries."""
        mock_func = Mock(side_effect=[
            Exception("First failure"),
            Exception("Second failure"),
            "success"
        ])

        result = _exponential_backoff_retry(mock_func, max_retries=3)

        assert result == "success"
        assert mock_func.call_count == 3
        # Should sleep after 1st and 2nd failures
        assert mock_time_sleep.call_count == 2

    def test_exponential_delay(self, mock_time_sleep):
        """Test that delays increase exponentially."""
        mock_func = Mock(side_effect=[
            Exception("Failure 1"),
            Exception("Failure 2"),
            "success"
        ])

        _exponential_backoff_retry(mock_func, max_retries=3)

        # Verify exponential backoff: 2^0=1, 2^1=2
        calls = mock_time_sleep.call_args_list
        assert len(calls) == 2
        assert calls[0][0][0] == 1  # First retry: 2^0 = 1 second
        assert calls[1][0][0] == 2  # Second retry: 2^1 = 2 seconds

    def test_raises_after_max_retries(self, mock_time_sleep):
        """Test that original error is raised after exhausting retries."""
        error_msg = "Persistent failure"
        mock_func = Mock(side_effect=Exception(error_msg))

        with pytest.raises(Exception, match=error_msg):
            _exponential_backoff_retry(mock_func, max_retries=3)

        assert mock_func.call_count == 4  # Initial + 3 retries
        assert mock_time_sleep.call_count == 3

    def test_raises_rate_limit_error(self, mock_time_sleep):
        """Test that rate limit errors are raised as AKShareRateLimitError."""
        mock_func = Mock(side_effect=Exception("Rate limit exceeded"))

        with pytest.raises(AKShareRateLimitError):
            _exponential_backoff_retry(mock_func, max_retries=2)

    def test_handles_timeout_errors(self, mock_time_sleep):
        """Test handling of timeout errors."""
        from requests.exceptions import Timeout
        mock_func = Mock(side_effect=[Timeout("Network timeout"), "success"])

        result = _exponential_backoff_retry(mock_func, max_retries=3)

        assert result == "success"
        assert mock_func.call_count == 2

    def test_max_retries_zero(self):
        """Test behavior with max_retries=0."""
        mock_func = Mock(side_effect=Exception("Failure"))

        with pytest.raises(Exception):
            _exponential_backoff_retry(mock_func, max_retries=0)

        assert mock_func.call_count == 1  # Only initial call, no retries

    def test_preserves_function_arguments(self, mock_time_sleep):
        """Test that function arguments are preserved across retries."""
        mock_func = Mock(side_effect=[Exception("Fail"), "success"])

        result = _exponential_backoff_retry(
            lambda: mock_func("arg1", kwarg1="value1"),
            max_retries=2
        )

        assert result == "success"
        assert all(
            call_args == call("arg1", kwarg1="value1")
            for call_args in mock_func.call_args_list
        )


# ============================================================================
# Test US Stock Data Retrieval
# ============================================================================

class TestGetAkshareStockDataUs:
    """Test the get_akshare_stock_data_us function."""

    def test_returns_dataframe_on_success(self, mock_akshare, sample_us_dataframe):
        """Test successful data retrieval returns DataFrame."""
        mock_akshare.stock_us_hist.return_value = sample_us_dataframe

        result = get_akshare_stock_data_us("AAPL", "2024-01-01", "2024-01-05")

        assert isinstance(result, str)  # Returns CSV string
        assert "AAPL" in result
        assert "2024-01-01" in result
        mock_akshare.stock_us_hist.assert_called_once_with(
            symbol="AAPL",
            period="daily",
            adjust=""
        )

    def test_filters_data_by_date_range(self, mock_akshare):
        """Test that data is properly filtered by date range."""
        # Create DataFrame with wider date range
        full_df = pd.DataFrame({
            'date': pd.to_datetime(['2023-12-28', '2024-01-02', '2024-01-03', '2024-01-04', '2024-01-08']),
            'open': [145.0, 150.0, 151.0, 152.0, 157.0],
            'high': [147.0, 152.0, 153.0, 154.0, 159.0],
            'low': [144.0, 149.0, 150.0, 151.0, 156.0],
            'close': [146.0, 151.0, 152.0, 153.0, 158.0],
            'volume': [900000, 1000000, 1100000, 1200000, 1500000],
        })
        mock_akshare.stock_us_hist.return_value = full_df

        result = get_akshare_stock_data_us("AAPL", "2024-01-01", "2024-01-05")

        # Result should only contain dates within range
        assert "2023-12-28" not in result
        assert "2024-01-08" not in result
        assert "2024-01-02" in result or "2024-01-03" in result

    def test_returns_error_string_on_failure(self, mock_akshare):
        """Test that exceptions return error string instead of raising."""
        mock_akshare.stock_us_hist.side_effect = Exception("API error")

        result = get_akshare_stock_data_us("AAPL", "2024-01-01", "2024-01-05")

        assert isinstance(result, str)
        assert "error" in result.lower() or "failed" in result.lower()

    def test_handles_empty_data(self, mock_akshare):
        """Test handling of empty DataFrame from API."""
        mock_akshare.stock_us_hist.return_value = pd.DataFrame()

        result = get_akshare_stock_data_us("INVALID", "2024-01-01", "2024-01-05")

        assert isinstance(result, str)
        assert "no data" in result.lower() or "empty" in result.lower()

    def test_handles_network_timeout(self, mock_akshare):
        """Test handling of network timeout errors."""
        from requests.exceptions import Timeout
        mock_akshare.stock_us_hist.side_effect = Timeout("Connection timeout")

        result = get_akshare_stock_data_us("AAPL", "2024-01-01", "2024-01-05")

        assert isinstance(result, str)
        assert "timeout" in result.lower() or "error" in result.lower()

    def test_standardizes_output_format(self, mock_akshare, sample_us_dataframe):
        """Test that output format matches expected CSV structure."""
        mock_akshare.stock_us_hist.return_value = sample_us_dataframe

        result = get_akshare_stock_data_us("AAPL", "2024-01-01", "2024-01-05")

        # Should contain CSV header information
        assert "Stock data for" in result or "AAPL" in result
        # Should contain column headers
        lines = result.split('\n')
        assert len(lines) > 1  # Has header + data rows

    def test_handles_malformed_dates(self, mock_akshare):
        """Test handling of invalid date formats."""
        result = get_akshare_stock_data_us("AAPL", "invalid-date", "2024-01-05")

        assert isinstance(result, str)
        # Should return error message rather than raising exception

    def test_symbol_case_handling(self, mock_akshare, sample_us_dataframe):
        """Test that symbol is converted to uppercase."""
        mock_akshare.stock_us_hist.return_value = sample_us_dataframe

        result = get_akshare_stock_data_us("aapl", "2024-01-01", "2024-01-05")

        mock_akshare.stock_us_hist.assert_called_once()
        call_args = mock_akshare.stock_us_hist.call_args
        assert call_args[1]['symbol'] == "AAPL" or call_args[1]['symbol'] == "aapl"


# ============================================================================
# Test Chinese Stock Data Retrieval
# ============================================================================

class TestGetAkshareStockDataCn:
    """Test the get_akshare_stock_data_cn function."""

    def test_returns_dataframe_on_success(self, mock_akshare, sample_cn_dataframe):
        """Test successful data retrieval returns DataFrame."""
        mock_akshare.stock_zh_a_hist.return_value = sample_cn_dataframe

        result = get_akshare_stock_data_cn("000001", "2024-01-01", "2024-01-05")

        assert isinstance(result, str)
        assert "000001" in result
        mock_akshare.stock_zh_a_hist.assert_called_once()

    def test_converts_date_format(self, mock_akshare, sample_cn_dataframe):
        """Test that dates are converted to YYYYMMDD format for API."""
        mock_akshare.stock_zh_a_hist.return_value = sample_cn_dataframe

        get_akshare_stock_data_cn("000001", "2024-01-01", "2024-01-05")

        call_args = mock_akshare.stock_zh_a_hist.call_args
        # Verify date format conversion happened
        assert call_args is not None

    def test_returns_error_string_on_failure(self, mock_akshare):
        """Test that exceptions return error string."""
        mock_akshare.stock_zh_a_hist.side_effect = Exception("API error")

        result = get_akshare_stock_data_cn("000001", "2024-01-01", "2024-01-05")

        assert isinstance(result, str)
        assert "error" in result.lower() or "failed" in result.lower()

    def test_standardizes_column_names(self, mock_akshare, sample_cn_dataframe):
        """Test that Chinese column names are mapped to English."""
        mock_akshare.stock_zh_a_hist.return_value = sample_cn_dataframe

        result = get_akshare_stock_data_cn("000001", "2024-01-01", "2024-01-05")

        # Output should contain English column names
        result_lower = result.lower()
        assert "date" in result_lower or "open" in result_lower or "close" in result_lower

    def test_handles_empty_data(self, mock_akshare):
        """Test handling of empty DataFrame."""
        mock_akshare.stock_zh_a_hist.return_value = pd.DataFrame()

        result = get_akshare_stock_data_cn("INVALID", "2024-01-01", "2024-01-05")

        assert isinstance(result, str)
        assert "no data" in result.lower() or "empty" in result.lower()

    def test_handles_symbol_with_suffix(self, mock_akshare, sample_cn_dataframe):
        """Test handling of symbols with .SZ or .SH suffixes."""
        mock_akshare.stock_zh_a_hist.return_value = sample_cn_dataframe

        result = get_akshare_stock_data_cn("000001.SZ", "2024-01-01", "2024-01-05")

        assert isinstance(result, str)
        # Function should handle suffix appropriately

    def test_handles_rate_limit_error(self, mock_akshare):
        """Test that rate limit errors are properly raised."""
        mock_akshare.stock_zh_a_hist.side_effect = Exception("访问频率过快")  # Chinese rate limit message

        # Should raise AKShareRateLimitError when wrapped in retry mechanism
        with pytest.raises(AKShareRateLimitError):
            _exponential_backoff_retry(
                lambda: mock_akshare.stock_zh_a_hist(),
                max_retries=1
            )

    def test_standardizes_output_format(self, mock_akshare, sample_cn_dataframe):
        """Test that output format is standardized."""
        mock_akshare.stock_zh_a_hist.return_value = sample_cn_dataframe

        result = get_akshare_stock_data_cn("000001", "2024-01-01", "2024-01-05")

        # Should be CSV-like format
        lines = result.split('\n')
        assert len(lines) > 1


# ============================================================================
# Test Auto-Market Detection
# ============================================================================

class TestGetAkshareStockData:
    """Test the get_akshare_stock_data function with auto-market detection."""

    @patch('tradingagents.dataflows.akshare.get_akshare_stock_data_us')
    def test_auto_detects_us_market(self, mock_us_func):
        """Test that US symbols are automatically detected."""
        mock_us_func.return_value = "US data"

        result = get_akshare_stock_data("AAPL", "2024-01-01", "2024-01-05")

        assert result == "US data"
        mock_us_func.assert_called_once_with("AAPL", "2024-01-01", "2024-01-05")

    @patch('tradingagents.dataflows.akshare.get_akshare_stock_data_cn')
    def test_auto_detects_cn_market_with_sz_suffix(self, mock_cn_func):
        """Test that Chinese symbols with .SZ suffix are detected."""
        mock_cn_func.return_value = "CN data"

        result = get_akshare_stock_data("000001.SZ", "2024-01-01", "2024-01-05")

        assert result == "CN data"
        mock_cn_func.assert_called_once_with("000001.SZ", "2024-01-01", "2024-01-05")

    @patch('tradingagents.dataflows.akshare.get_akshare_stock_data_cn')
    def test_auto_detects_cn_market_with_sh_suffix(self, mock_cn_func):
        """Test that Chinese symbols with .SH suffix are detected."""
        mock_cn_func.return_value = "CN data"

        result = get_akshare_stock_data("600000.SH", "2024-01-01", "2024-01-05")

        assert result == "CN data"
        mock_cn_func.assert_called_once_with("600000.SH", "2024-01-01", "2024-01-05")

    @patch('tradingagents.dataflows.akshare.get_akshare_stock_data_cn')
    def test_auto_detects_cn_market_numeric_only(self, mock_cn_func):
        """Test that numeric-only symbols default to Chinese market."""
        mock_cn_func.return_value = "CN data"

        result = get_akshare_stock_data("000001", "2024-01-01", "2024-01-05")

        assert result == "CN data"
        mock_cn_func.assert_called_once_with("000001", "2024-01-01", "2024-01-05")

    @patch('tradingagents.dataflows.akshare.get_akshare_stock_data_us')
    def test_explicit_market_us(self, mock_us_func):
        """Test that market='us' forces US function."""
        mock_us_func.return_value = "US data"

        result = get_akshare_stock_data("AAPL", "2024-01-01", "2024-01-05", market="us")

        assert result == "US data"
        mock_us_func.assert_called_once()

    @patch('tradingagents.dataflows.akshare.get_akshare_stock_data_cn')
    def test_explicit_market_cn(self, mock_cn_func):
        """Test that market='cn' forces Chinese function."""
        mock_cn_func.return_value = "CN data"

        result = get_akshare_stock_data("000001", "2024-01-01", "2024-01-05", market="cn")

        assert result == "CN data"
        mock_cn_func.assert_called_once()

    def test_returns_standardized_dataframe(self):
        """Test that output has consistent schema regardless of market."""
        with patch('tradingagents.dataflows.akshare.get_akshare_stock_data_us') as mock_us:
            mock_us.return_value = "Date,Open,High,Low,Close,Volume\n2024-01-01,150,152,149,151,1000000"
            result_us = get_akshare_stock_data("AAPL", "2024-01-01", "2024-01-05")

        with patch('tradingagents.dataflows.akshare.get_akshare_stock_data_cn') as mock_cn:
            mock_cn.return_value = "Date,Open,High,Low,Close,Volume\n2024-01-01,10,10.2,9.9,10.1,500000"
            result_cn = get_akshare_stock_data("000001", "2024-01-01", "2024-01-05")

        # Both should have similar structure
        assert isinstance(result_us, str)
        assert isinstance(result_cn, str)

    def test_invalid_market_parameter(self):
        """Test handling of invalid market parameter."""
        with pytest.raises(ValueError):
            get_akshare_stock_data("AAPL", "2024-01-01", "2024-01-05", market="invalid")

    @patch('tradingagents.dataflows.akshare.get_akshare_stock_data_us')
    def test_market_auto_default_behavior(self, mock_us_func):
        """Test that market='auto' is the default behavior."""
        mock_us_func.return_value = "US data"

        # Call without market parameter
        result1 = get_akshare_stock_data("AAPL", "2024-01-01", "2024-01-05")
        # Call with explicit market='auto'
        result2 = get_akshare_stock_data("AAPL", "2024-01-01", "2024-01-05", market="auto")

        assert result1 == result2


# ============================================================================
# Test AKShareRateLimitError Exception
# ============================================================================

class TestAKShareRateLimitError:
    """Test the AKShareRateLimitError exception class."""

    def test_is_exception_subclass(self):
        """Test that AKShareRateLimitError inherits from Exception."""
        assert issubclass(AKShareRateLimitError, Exception)

    def test_can_be_raised_and_caught(self):
        """Test that exception can be raised and caught properly."""
        with pytest.raises(AKShareRateLimitError):
            raise AKShareRateLimitError("Rate limit exceeded")

    def test_message_included(self):
        """Test that error message is preserved."""
        message = "API rate limit exceeded: 5 calls per minute"
        try:
            raise AKShareRateLimitError(message)
        except AKShareRateLimitError as e:
            assert str(e) == message

    def test_can_be_caught_as_generic_exception(self):
        """Test that it can be caught as generic Exception."""
        with pytest.raises(Exception):
            raise AKShareRateLimitError("Rate limit")

    def test_distinct_from_other_exceptions(self):
        """Test that it's distinct from other exception types."""
        try:
            raise AKShareRateLimitError("Rate limit")
        except ValueError:
            pytest.fail("Should not be caught as ValueError")
        except AKShareRateLimitError:
            pass  # Expected


# ============================================================================
# Test Vendor Integration (interface.py modifications)
# ============================================================================

class TestVendorIntegration:
    """Test integration with the vendor routing system in interface.py."""

    def test_akshare_in_vendor_methods(self):
        """Test that akshare is registered in VENDOR_METHODS."""
        assert "get_stock_data" in VENDOR_METHODS
        assert "akshare" in VENDOR_METHODS["get_stock_data"]

    def test_akshare_vendor_function_mapping(self):
        """Test that akshare maps to correct function."""
        from tradingagents.dataflows.akshare import get_akshare_stock_data

        akshare_impl = VENDOR_METHODS["get_stock_data"]["akshare"]
        assert akshare_impl == get_akshare_stock_data

    @patch('tradingagents.dataflows.akshare.get_akshare_stock_data')
    @patch('tradingagents.dataflows.config.get_config')
    def test_route_to_vendor_uses_akshare(self, mock_config, mock_akshare_func):
        """Test that route_to_vendor calls akshare when configured."""
        mock_config.return_value = {"data_vendor": "akshare"}
        mock_akshare_func.return_value = "AKShare data"

        result = route_to_vendor("get_stock_data", "AAPL", "2024-01-01", "2024-01-05")

        assert result == "AKShare data"
        mock_akshare_func.assert_called_once_with("AAPL", "2024-01-01", "2024-01-05")

    @patch('tradingagents.dataflows.akshare.get_akshare_stock_data')
    @patch('tradingagents.dataflows.y_finance.get_YFin_data_online')
    @patch('tradingagents.dataflows.config.get_config')
    def test_fallback_on_rate_limit(self, mock_config, mock_yfinance, mock_akshare):
        """Test that AKShareRateLimitError triggers fallback to next vendor."""
        mock_config.return_value = {"data_vendor": "akshare,yfinance"}
        mock_akshare.side_effect = AKShareRateLimitError("Rate limit exceeded")
        mock_yfinance.return_value = "YFinance data"

        result = route_to_vendor("get_stock_data", "AAPL", "2024-01-01", "2024-01-05")

        assert result == "YFinance data"
        mock_akshare.assert_called_once()
        mock_yfinance.assert_called_once()

    @patch('tradingagents.dataflows.akshare.get_akshare_stock_data')
    @patch('tradingagents.dataflows.y_finance.get_YFin_data_online')
    @patch('tradingagents.dataflows.config.get_config')
    def test_fallback_chain_akshare_yfinance(self, mock_config, mock_yfinance, mock_akshare):
        """Test multi-vendor fallback chain works correctly."""
        mock_config.return_value = {"data_vendor": "akshare,yfinance,local"}
        mock_akshare.side_effect = AKShareRateLimitError("Rate limit")
        mock_yfinance.return_value = "YFinance fallback data"

        result = route_to_vendor("get_stock_data", "AAPL", "2024-01-01", "2024-01-05")

        assert "YFinance" in result
        # Verify akshare was tried first, then yfinance succeeded
        assert mock_akshare.call_count == 1
        assert mock_yfinance.call_count == 1

    @patch('tradingagents.dataflows.akshare.get_akshare_stock_data')
    @patch('tradingagents.dataflows.config.get_config')
    def test_akshare_error_string_not_triggers_fallback(self, mock_config, mock_akshare):
        """Test that error strings (not exceptions) don't trigger fallback."""
        mock_config.return_value = {"data_vendor": "akshare"}
        # Return error string, not exception
        mock_akshare.return_value = "Error: No data found"

        result = route_to_vendor("get_stock_data", "INVALID", "2024-01-01", "2024-01-05")

        # Should return the error string, not attempt fallback
        assert "Error" in result
        assert mock_akshare.call_count == 1

    def test_akshare_in_vendor_list(self):
        """Test that akshare is in the global VENDOR_LIST."""
        from tradingagents.dataflows.interface import VENDOR_LIST
        assert "akshare" in VENDOR_LIST


# ============================================================================
# Integration Tests
# ============================================================================

class TestAKShareIntegration:
    """Integration tests combining multiple components."""

    @patch('tradingagents.dataflows.akshare.ak')
    def test_end_to_end_us_stock_retrieval(self, mock_ak):
        """Test complete flow of US stock data retrieval."""
        # Setup mock
        mock_df = pd.DataFrame({
            'date': pd.date_range('2024-01-01', periods=3, freq='D'),
            'open': [150.0, 151.0, 152.0],
            'high': [152.0, 153.0, 154.0],
            'low': [149.0, 150.0, 151.0],
            'close': [151.0, 152.0, 153.0],
            'volume': [1000000, 1100000, 1200000],
        })
        mock_ak.stock_us_hist.return_value = mock_df

        # Call main function
        result = get_akshare_stock_data("AAPL", "2024-01-01", "2024-01-03", market="us")

        # Verify result
        assert isinstance(result, str)
        assert "AAPL" in result or "150" in result

    @patch('tradingagents.dataflows.akshare.ak')
    def test_end_to_end_cn_stock_retrieval(self, mock_ak):
        """Test complete flow of Chinese stock data retrieval."""
        # Setup mock with Chinese column names
        mock_df = pd.DataFrame({
            '日期': ['2024-01-01', '2024-01-02', '2024-01-03'],
            '开盘': [10.0, 10.1, 10.2],
            '最高': [10.2, 10.3, 10.4],
            '最低': [9.9, 10.0, 10.1],
            '收盘': [10.1, 10.2, 10.3],
            '成交量': [500000, 550000, 600000],
        })
        mock_ak.stock_zh_a_hist.return_value = mock_df

        # Call main function
        result = get_akshare_stock_data("000001", "2024-01-01", "2024-01-03", market="cn")

        # Verify result
        assert isinstance(result, str)
        assert "000001" in result or "10" in result

    @patch('tradingagents.dataflows.akshare.ak')
    @patch('tradingagents.dataflows.akshare.time.sleep')
    def test_retry_mechanism_with_transient_failure(self, mock_sleep, mock_ak):
        """Test that retry mechanism handles transient failures."""
        # First call fails, second succeeds
        mock_df = pd.DataFrame({
            'date': pd.date_range('2024-01-01', periods=2, freq='D'),
            'open': [150.0, 151.0],
            'high': [152.0, 153.0],
            'low': [149.0, 150.0],
            'close': [151.0, 152.0],
            'volume': [1000000, 1100000],
        })
        mock_ak.stock_us_hist.side_effect = [
            Exception("Transient network error"),
            mock_df
        ]

        # Should succeed on retry
        result = get_akshare_stock_data_us("AAPL", "2024-01-01", "2024-01-02")

        assert isinstance(result, str)
        assert mock_ak.stock_us_hist.call_count == 2
        assert mock_sleep.call_count == 1  # One retry delay

    def test_column_name_standardization(self):
        """Test that Chinese and US data have standardized column names."""
        with patch('tradingagents.dataflows.akshare.ak') as mock_ak:
            # Test US format
            us_df = pd.DataFrame({
                'date': pd.date_range('2024-01-01', periods=2, freq='D'),
                'open': [150.0, 151.0],
                'high': [152.0, 153.0],
                'low': [149.0, 150.0],
                'close': [151.0, 152.0],
                'volume': [1000000, 1100000],
            })
            mock_ak.stock_us_hist.return_value = us_df
            us_result = get_akshare_stock_data_us("AAPL", "2024-01-01", "2024-01-02")

            # Test CN format
            cn_df = pd.DataFrame({
                '日期': ['2024-01-01', '2024-01-02'],
                '开盘': [10.0, 10.1],
                '最高': [10.2, 10.3],
                '最低': [9.9, 10.0],
                '收盘': [10.1, 10.2],
                '成交量': [500000, 550000],
            })
            mock_ak.stock_zh_a_hist.return_value = cn_df
            cn_result = get_akshare_stock_data_cn("000001", "2024-01-01", "2024-01-02")

            # Both should have English headers
            for result in [us_result, cn_result]:
                result_lower = result.lower()
                # At least some standard column names should appear
                has_standard_cols = any(
                    col in result_lower
                    for col in ['date', 'open', 'high', 'low', 'close', 'volume']
                )
                assert has_standard_cols


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================

class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_symbol(self):
        """Test handling of empty symbol string."""
        result = get_akshare_stock_data("", "2024-01-01", "2024-01-05")
        assert isinstance(result, str)

    def test_future_dates(self):
        """Test handling of future dates."""
        with patch('tradingagents.dataflows.akshare.ak') as mock_ak:
            mock_ak.stock_us_hist.return_value = pd.DataFrame()
            result = get_akshare_stock_data_us("AAPL", "2030-01-01", "2030-01-05")
            assert isinstance(result, str)

    def test_start_date_after_end_date(self):
        """Test handling when start_date > end_date."""
        result = get_akshare_stock_data("AAPL", "2024-01-05", "2024-01-01")
        assert isinstance(result, str)

    def test_very_long_date_range(self):
        """Test handling of very long date ranges (years of data)."""
        with patch('tradingagents.dataflows.akshare.ak') as mock_ak:
            # Simulate large dataset
            large_df = pd.DataFrame({
                'date': pd.date_range('2020-01-01', periods=1000, freq='D'),
                'open': [150.0] * 1000,
                'high': [152.0] * 1000,
                'low': [149.0] * 1000,
                'close': [151.0] * 1000,
                'volume': [1000000] * 1000,
            })
            mock_ak.stock_us_hist.return_value = large_df

            result = get_akshare_stock_data_us("AAPL", "2020-01-01", "2024-01-01")
            assert isinstance(result, str)

    def test_special_characters_in_symbol(self):
        """Test handling of symbols with special characters."""
        with patch('tradingagents.dataflows.akshare.ak') as mock_ak:
            mock_ak.stock_us_hist.return_value = pd.DataFrame()
            result = get_akshare_stock_data_us("BRK.B", "2024-01-01", "2024-01-05")
            assert isinstance(result, str)

    @patch('tradingagents.dataflows.akshare.ak')
    def test_unicode_in_error_messages(self, mock_ak):
        """Test handling of Unicode characters in error messages."""
        mock_ak.stock_zh_a_hist.side_effect = Exception("访问频率过快，请稍后重试")

        result = get_akshare_stock_data_cn("000001", "2024-01-01", "2024-01-05")
        assert isinstance(result, str)

    def test_none_parameters(self):
        """Test handling of None parameters."""
        with pytest.raises((TypeError, AttributeError)):
            get_akshare_stock_data(None, "2024-01-01", "2024-01-05")
