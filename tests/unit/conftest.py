"""
Unit test specific fixtures for TradingAgents.

This module provides fixtures specific to unit tests:
- Data vendor mocking (akshare, yfinance)
- Sample DataFrames for testing
- Time/sleep mocking for retry tests
- HTTP request mocking
- Subprocess mocking

These fixtures are only available in tests/unit/ directory.
For shared fixtures, see tests/conftest.py.

Scope:
- function: Default scope for isolation between tests
"""

import pytest
import pandas as pd
from unittest.mock import Mock, patch
from datetime import datetime


# ============================================================================
# Data Vendor Mocking Fixtures
# ============================================================================

@pytest.fixture
def mock_akshare():
    """
    Mock akshare module for testing data fetching.

    Provides a mocked akshare module that avoids actual API calls.
    Configure return values on the mock as needed per test.

    Scope: function (default)

    Yields:
        Mock: Mocked akshare module (as 'ak')

    Example:
        def test_akshare_fetch(mock_akshare):
            mock_akshare.stock_us_hist.return_value = pd.DataFrame(...)
            # Test code using akshare
    """
    with patch('tradingagents.dataflows.akshare.ak') as mock_ak:
        yield mock_ak


@pytest.fixture
def mock_yfinance():
    """
    Mock yfinance module for testing data fetching.

    Provides a mocked yfinance module that avoids actual API calls.
    Configure return values on the mock as needed per test.

    Scope: function (default)

    Yields:
        Mock: Mocked yfinance module

    Example:
        def test_yfinance_fetch(mock_yfinance):
            mock_ticker = Mock()
            mock_yfinance.Ticker.return_value = mock_ticker
            mock_ticker.history.return_value = pd.DataFrame(...)
    """
    with patch('tradingagents.dataflows.yfinance.yf') as mock_yf:
        yield mock_yf


# ============================================================================
# Sample Data Fixtures
# ============================================================================

@pytest.fixture
def sample_dataframe():
    """
    Create a sample standardized DataFrame for testing.

    Provides a DataFrame with standard column names (Date, Open, High, Low, Close, Volume)
    suitable for testing data processing functions.

    Scope: function (default)

    Returns:
        pd.DataFrame: Sample stock data with 5 rows

    Example:
        def test_data_processing(sample_dataframe):
            df = sample_dataframe
            assert len(df) == 5
            assert "Date" in df.columns
    """
    return pd.DataFrame({
        'Date': pd.date_range('2024-01-01', periods=5, freq='D'),
        'Open': [150.0, 151.0, 152.0, 153.0, 154.0],
        'High': [152.0, 153.0, 154.0, 155.0, 156.0],
        'Low': [149.0, 150.0, 151.0, 152.0, 153.0],
        'Close': [151.0, 152.0, 153.0, 154.0, 155.0],
        'Volume': [1000000, 1100000, 1200000, 1300000, 1400000]
    })


# ============================================================================
# Time/Sleep Mocking Fixtures
# ============================================================================

@pytest.fixture
def mock_time_sleep():
    """
    Mock time.sleep to speed up retry/delay tests.

    Prevents actual delays during testing, making tests run faster.
    Useful for testing retry logic and rate limiting.

    Scope: function (default)

    Yields:
        Mock: Mocked time.sleep function

    Example:
        def test_retry_logic(mock_time_sleep):
            # Code with time.sleep() won't actually sleep
            retry_operation()
            assert mock_time_sleep.call_count == 3  # Retried 3 times
    """
    with patch('tradingagents.dataflows.akshare.time.sleep') as mock_sleep:
        yield mock_sleep


# ============================================================================
# HTTP Request Mocking Fixtures
# ============================================================================

@pytest.fixture
def mock_requests():
    """
    Mock requests module for testing HTTP operations.

    Provides a mocked requests module that avoids actual network calls.
    Configure responses on the mock as needed per test.

    Scope: function (default)

    Yields:
        Mock: Mocked requests module

    Example:
        def test_api_call(mock_requests):
            mock_response = Mock()
            mock_response.json.return_value = {"data": "test"}
            mock_response.status_code = 200
            mock_requests.get.return_value = mock_response
    """
    with patch('requests') as mock_req:
        yield mock_req


# ============================================================================
# Subprocess Mocking Fixtures
# ============================================================================

@pytest.fixture
def mock_subprocess():
    """
    Mock subprocess module for testing external command execution.

    Provides a mocked subprocess module that avoids actual command execution.
    Configure return values and side effects as needed per test.

    Scope: function (default)

    Yields:
        Mock: Mocked subprocess module

    Example:
        def test_external_command(mock_subprocess):
            mock_subprocess.run.return_value = Mock(returncode=0, stdout="success")
            result = run_external_tool()
            assert mock_subprocess.run.called
    """
    with patch('subprocess') as mock_sub:
        yield mock_sub
