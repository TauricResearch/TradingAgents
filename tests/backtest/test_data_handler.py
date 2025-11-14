"""
Tests for the HistoricalDataHandler class.
"""

import pytest
from decimal import Decimal
from datetime import datetime, timedelta
import pandas as pd

from tradingagents.backtest import BacktestConfig, HistoricalDataHandler
from tradingagents.backtest.exceptions import (
    DataNotFoundError,
    DataQualityError,
    LookAheadBiasError,
)


@pytest.fixture
def config():
    """Create test configuration."""
    return BacktestConfig(
        initial_capital=Decimal("100000"),
        start_date="2022-01-01",
        end_date="2022-12-31",
        cache_data=False,  # Disable caching for tests
    )


@pytest.fixture
def data_handler(config):
    """Create data handler."""
    return HistoricalDataHandler(config)


def test_data_handler_initialization(data_handler):
    """Test data handler initialization."""
    assert data_handler is not None
    assert data_handler.data == {}
    assert data_handler.current_time is None


def test_ticker_validation():
    """Test ticker validation."""
    from tradingagents.security.validators import validate_ticker

    # Valid tickers
    assert validate_ticker("AAPL") == "AAPL"
    assert validate_ticker("brk.a") == "BRK.A"
    assert validate_ticker("RDS-B") == "RDS-B"

    # Invalid tickers
    with pytest.raises(ValueError):
        validate_ticker("../etc/passwd")

    with pytest.raises(ValueError):
        validate_ticker("INVALID!" * 100)  # Too long


def test_look_ahead_bias_prevention(data_handler):
    """Test that look-ahead bias is prevented."""
    # Set current time
    current_time = datetime(2022, 6, 1)
    data_handler.set_current_time(current_time)

    # Trying to access future data should raise error
    # (This test would need mocked data to work properly)
    pass


def test_data_alignment():
    """Test data alignment across multiple tickers."""
    # Would need mocked data
    pass


def test_missing_data_handling():
    """Test handling of missing data."""
    pass


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
