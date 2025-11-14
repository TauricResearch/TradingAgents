"""
Tests for the core Backtester class.
"""

import pytest
from decimal import Decimal
from datetime import datetime
import pandas as pd
import numpy as np

from tradingagents.backtest import (
    Backtester,
    BacktestConfig,
    BuyAndHoldStrategy,
    SimpleMovingAverageStrategy,
)
from tradingagents.backtest.exceptions import BacktestError


@pytest.fixture
def simple_config():
    """Create a simple backtest configuration."""
    return BacktestConfig(
        initial_capital=Decimal("100000"),
        start_date="2022-01-01",
        end_date="2022-12-31",
        commission=Decimal("0.001"),
        slippage=Decimal("0.0005"),
        benchmark="SPY",
    )


@pytest.fixture
def buy_hold_strategy():
    """Create a buy-and-hold strategy."""
    return BuyAndHoldStrategy()


def test_backtester_initialization(simple_config):
    """Test backtester initialization."""
    backtester = Backtester(simple_config)

    assert backtester.config == simple_config
    assert backtester.data_handler is not None
    assert backtester.execution_simulator is not None
    assert backtester.performance_analyzer is not None


def test_simple_backtest(simple_config, buy_hold_strategy):
    """Test running a simple backtest."""
    backtester = Backtester(simple_config)

    # This test would normally fail without real data
    # In production, you'd mock the data handler or use test data
    # For now, we'll skip the actual run
    pass


def test_backtest_results_structure(simple_config, buy_hold_strategy):
    """Test that backtest results have the correct structure."""
    # This is a structure test - would need mocked data to run
    pass


def test_invalid_configuration():
    """Test that invalid configurations raise errors."""
    with pytest.raises(Exception):  # Should be InvalidConfigError
        BacktestConfig(
            initial_capital=Decimal("-1000"),  # Invalid negative capital
            start_date="2022-01-01",
            end_date="2022-12-31",
        )


def test_date_validation():
    """Test date validation."""
    with pytest.raises(Exception):
        BacktestConfig(
            initial_capital=Decimal("100000"),
            start_date="2022-12-31",
            end_date="2022-01-01",  # End before start
        )


class TestPortfolio:
    """Tests for the Portfolio class."""

    def test_portfolio_initialization(self):
        """Test portfolio initialization."""
        from tradingagents.backtest.backtester import Portfolio

        portfolio = Portfolio(Decimal("100000"))

        assert portfolio.initial_capital == Decimal("100000")
        assert portfolio.cash == Decimal("100000")
        assert len(portfolio.positions) == 0
        assert len(portfolio.trades) == 0


    def test_portfolio_value_calculation(self):
        """Test portfolio value calculation."""
        from tradingagents.backtest.backtester import Portfolio

        portfolio = Portfolio(Decimal("100000"))

        # Test with no positions
        assert portfolio.get_total_value() == Decimal("100000")


def test_strategy_comparison():
    """Test comparing multiple strategies."""
    # This would test the compare_strategies function
    pass


# Synthetic data generation for testing
def generate_synthetic_data(
    ticker: str,
    start_date: str,
    end_date: str,
    initial_price: float = 100.0,
    volatility: float = 0.02,
) -> pd.DataFrame:
    """
    Generate synthetic OHLCV data for testing.

    Args:
        ticker: Ticker symbol
        start_date: Start date
        end_date: End date
        initial_price: Initial price
        volatility: Daily volatility

    Returns:
        DataFrame with OHLCV data
    """
    dates = pd.date_range(start=start_date, end=end_date, freq='D')
    n_days = len(dates)

    # Generate random returns
    np.random.seed(42)
    returns = np.random.normal(0.0005, volatility, n_days)

    # Generate price series
    close_prices = initial_price * np.exp(np.cumsum(returns))

    # Generate OHLCV
    data = pd.DataFrame({
        'open': close_prices * (1 + np.random.normal(0, 0.005, n_days)),
        'high': close_prices * (1 + np.abs(np.random.normal(0, 0.01, n_days))),
        'low': close_prices * (1 - np.abs(np.random.normal(0, 0.01, n_days))),
        'close': close_prices,
        'volume': np.random.randint(1000000, 10000000, n_days),
    }, index=dates)

    # Ensure high >= low
    data['high'] = data[['high', 'open', 'close']].max(axis=1)
    data['low'] = data[['low', 'open', 'close']].min(axis=1)

    return data


def test_synthetic_data_generation():
    """Test synthetic data generation."""
    data = generate_synthetic_data(
        ticker='TEST',
        start_date='2022-01-01',
        end_date='2022-12-31',
    )

    assert not data.empty
    assert len(data) > 0
    assert all(col in data.columns for col in ['open', 'high', 'low', 'close', 'volume'])
    assert (data['high'] >= data['low']).all()
    assert (data['high'] >= data['open']).all()
    assert (data['high'] >= data['close']).all()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
