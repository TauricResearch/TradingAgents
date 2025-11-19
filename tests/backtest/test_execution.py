"""
Tests for the ExecutionSimulator class.
"""

import pytest
from decimal import Decimal
from datetime import datetime

from tradingagents.backtest import BacktestConfig
from tradingagents.backtest.execution import (
    ExecutionSimulator,
    Order,
    OrderSide,
    OrderType,
    OrderStatus,
    create_market_order,
)
from tradingagents.backtest.exceptions import (
    InsufficientCapitalError,
    InvalidOrderError,
)


@pytest.fixture
def config():
    """Create test configuration."""
    return BacktestConfig(
        initial_capital=Decimal("100000"),
        start_date="2022-01-01",
        end_date="2022-12-31",
        commission=Decimal("0.001"),
        slippage=Decimal("0.0005"),
    )


@pytest.fixture
def executor(config):
    """Create execution simulator."""
    return ExecutionSimulator(config)


def test_executor_initialization(executor):
    """Test executor initialization."""
    assert executor is not None
    assert len(executor.fills) == 0
    assert executor.order_count == 0


def test_create_market_order():
    """Test market order creation."""
    order = create_market_order(
        ticker="AAPL",
        side=OrderSide.BUY,
        quantity=Decimal("100"),
        timestamp=datetime.now(),
    )

    assert order.ticker == "AAPL"
    assert order.side == OrderSide.BUY
    assert order.quantity == Decimal("100")
    assert order.order_type == OrderType.MARKET


def test_invalid_order():
    """Test that invalid orders raise errors."""
    with pytest.raises(InvalidOrderError):
        Order(
            ticker="AAPL",
            side=OrderSide.BUY,
            quantity=Decimal("-100"),  # Negative quantity
            order_type=OrderType.MARKET,
            timestamp=datetime.now(),
        )


def test_order_execution(executor):
    """Test basic order execution."""
    order = create_market_order(
        ticker="AAPL",
        side=OrderSide.BUY,
        quantity=Decimal("100"),
        timestamp=datetime.now(),
    )

    current_price = Decimal("150.00")
    current_volume = Decimal("1000000")
    available_capital = Decimal("100000")

    filled_order = executor.execute_order(
        order,
        current_price,
        current_volume,
        available_capital,
    )

    assert filled_order.is_filled or filled_order.is_partially_filled
    assert filled_order.filled_quantity > 0
    assert filled_order.commission > 0


def test_insufficient_capital(executor):
    """Test insufficient capital handling."""
    order = create_market_order(
        ticker="AAPL",
        side=OrderSide.BUY,
        quantity=Decimal("10000"),  # Too many shares
        timestamp=datetime.now(),
    )

    current_price = Decimal("150.00")
    current_volume = Decimal("1000000")
    available_capital = Decimal("1000")  # Not enough

    with pytest.raises(InsufficientCapitalError):
        executor.execute_order(
            order,
            current_price,
            current_volume,
            available_capital,
        )


def test_commission_calculation(executor):
    """Test commission calculation."""
    quantity = Decimal("100")
    price = Decimal("150.00")

    commission = executor._calculate_commission(quantity, price)

    # Should be percentage-based: 100 * 150 * 0.001 = 15
    expected = quantity * price * executor.config.commission
    assert commission == expected


def test_slippage_calculation(executor):
    """Test slippage calculation."""
    order = create_market_order(
        ticker="AAPL",
        side=OrderSide.BUY,
        quantity=Decimal("100"),
        timestamp=datetime.now(),
    )

    current_price = Decimal("150.00")
    current_volume = Decimal("1000000")

    fill_price = executor._calculate_fill_price(
        order,
        current_price,
        current_volume,
    )

    # Buy order should have positive slippage
    assert fill_price >= current_price


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
