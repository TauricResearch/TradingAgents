"""
Pytest configuration and shared fixtures for TradingAgents tests.

This module provides common fixtures, test utilities, and configuration
that are shared across all test modules.
"""

import os
import pytest
from decimal import Decimal
from datetime import datetime
from unittest.mock import Mock, MagicMock
from typing import Dict, Any

from tradingagents.brokers.base import (
    BrokerAccount,
    BrokerPosition,
    BrokerOrder,
    OrderSide,
    OrderType,
    OrderStatus,
)


# ============================================================================
# Environment Setup
# ============================================================================

@pytest.fixture(autouse=True)
def clean_environment():
    """Clean environment variables before each test."""
    # Store original environment
    original_env = os.environ.copy()

    # Yield to test
    yield

    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def mock_env_vars():
    """Fixture providing mock environment variables."""
    return {
        "OPENAI_API_KEY": "test-openai-key",
        "ANTHROPIC_API_KEY": "test-anthropic-key",
        "GOOGLE_API_KEY": "test-google-key",
        "ALPACA_API_KEY": "test-alpaca-key",
        "ALPACA_SECRET_KEY": "test-alpaca-secret",
        "ALPACA_PAPER_TRADING": "true",
    }


# ============================================================================
# Broker Test Fixtures
# ============================================================================

@pytest.fixture
def sample_broker_account():
    """Fixture providing a sample broker account."""
    return BrokerAccount(
        account_number="ACC123456",
        cash=Decimal("50000.00"),
        buying_power=Decimal("200000.00"),
        portfolio_value=Decimal("75000.00"),
        equity=Decimal("75000.00"),
        last_equity=Decimal("74500.00"),
        multiplier=Decimal("4"),
        currency="USD",
        pattern_day_trader=False
    )


@pytest.fixture
def sample_broker_position():
    """Fixture providing a sample broker position."""
    return BrokerPosition(
        symbol="AAPL",
        quantity=Decimal("100"),
        avg_entry_price=Decimal("150.00"),
        current_price=Decimal("155.00"),
        market_value=Decimal("15500.00"),
        unrealized_pnl=Decimal("500.00"),
        unrealized_pnl_percent=Decimal("0.0333"),
        cost_basis=Decimal("15000.00")
    )


@pytest.fixture
def sample_positions_list(sample_broker_position):
    """Fixture providing a list of sample positions."""
    return [
        sample_broker_position,
        BrokerPosition(
            symbol="TSLA",
            quantity=Decimal("50"),
            avg_entry_price=Decimal("250.00"),
            current_price=Decimal("240.00"),
            market_value=Decimal("12000.00"),
            unrealized_pnl=Decimal("-500.00"),
            unrealized_pnl_percent=Decimal("-0.04"),
            cost_basis=Decimal("12500.00")
        ),
        BrokerPosition(
            symbol="NVDA",
            quantity=Decimal("25"),
            avg_entry_price=Decimal("800.00"),
            current_price=Decimal("850.00"),
            market_value=Decimal("21250.00"),
            unrealized_pnl=Decimal("1250.00"),
            unrealized_pnl_percent=Decimal("0.0625"),
            cost_basis=Decimal("20000.00")
        )
    ]


@pytest.fixture
def sample_market_order():
    """Fixture providing a sample market order."""
    return BrokerOrder(
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=Decimal("100"),
        order_type=OrderType.MARKET,
        time_in_force="day"
    )


@pytest.fixture
def sample_limit_order():
    """Fixture providing a sample limit order."""
    return BrokerOrder(
        symbol="TSLA",
        side=OrderSide.SELL,
        quantity=Decimal("50"),
        order_type=OrderType.LIMIT,
        limit_price=Decimal("250.50"),
        time_in_force="gtc"
    )


@pytest.fixture
def sample_filled_order():
    """Fixture providing a sample filled order."""
    return BrokerOrder(
        symbol="NVDA",
        side=OrderSide.BUY,
        quantity=Decimal("25"),
        order_type=OrderType.MARKET,
        order_id="order-123",
        status=OrderStatus.FILLED,
        filled_qty=Decimal("25"),
        filled_price=Decimal("850.00"),
        submitted_at=datetime(2024, 1, 15, 10, 30, 0),
        filled_at=datetime(2024, 1, 15, 10, 30, 5)
    )


# ============================================================================
# Mock Broker Factory
# ============================================================================

class MockBrokerFactory:
    """Factory for creating mock brokers with various behaviors."""

    @staticmethod
    def create_connected_broker(account=None, positions=None):
        """Create a mock broker that is connected."""
        broker = Mock()
        broker.connected = True
        broker.paper_trading = True

        # Set up account
        if account is None:
            account = BrokerAccount(
                account_number="ACC123456",
                cash=Decimal("50000.00"),
                buying_power=Decimal("200000.00"),
                portfolio_value=Decimal("75000.00"),
                equity=Decimal("75000.00"),
                last_equity=Decimal("74500.00"),
                multiplier=Decimal("4")
            )
        broker.get_account.return_value = account

        # Set up positions
        if positions is None:
            positions = []
        broker.get_positions.return_value = positions

        # Set up order methods
        def mock_submit_order(order):
            order.order_id = f"order-{id(order)}"
            order.status = OrderStatus.SUBMITTED
            order.submitted_at = datetime.now()
            return order

        broker.submit_order.side_effect = mock_submit_order
        broker.buy_market.side_effect = lambda symbol, qty: mock_submit_order(
            BrokerOrder(symbol=symbol, side=OrderSide.BUY, quantity=qty, order_type=OrderType.MARKET)
        )
        broker.sell_market.side_effect = lambda symbol, qty: mock_submit_order(
            BrokerOrder(symbol=symbol, side=OrderSide.SELL, quantity=qty, order_type=OrderType.MARKET)
        )

        return broker

    @staticmethod
    def create_disconnected_broker():
        """Create a mock broker that is not connected."""
        broker = Mock()
        broker.connected = False
        broker.paper_trading = True
        return broker

    @staticmethod
    def create_failing_broker():
        """Create a mock broker that fails on all operations."""
        broker = Mock()
        broker.connected = True
        broker.get_account.side_effect = Exception("Broker error")
        broker.get_positions.side_effect = Exception("Broker error")
        broker.submit_order.side_effect = Exception("Broker error")
        return broker


@pytest.fixture
def mock_broker_factory():
    """Fixture providing the MockBrokerFactory."""
    return MockBrokerFactory


@pytest.fixture
def connected_broker(sample_broker_account, sample_positions_list):
    """Fixture providing a connected mock broker."""
    return MockBrokerFactory.create_connected_broker(
        account=sample_broker_account,
        positions=sample_positions_list
    )


# ============================================================================
# LLM Test Utilities
# ============================================================================

@pytest.fixture
def mock_llm():
    """Fixture providing a mock LLM instance."""
    llm = Mock()
    llm.invoke.return_value = Mock(content="Test response")
    return llm


@pytest.fixture
def mock_openai_llm():
    """Fixture providing a mock OpenAI LLM."""
    llm = Mock()
    llm.model_name = "gpt-4o"
    llm.temperature = 1.0
    return llm


@pytest.fixture
def mock_anthropic_llm():
    """Fixture providing a mock Anthropic LLM."""
    llm = Mock()
    llm.model = "claude-3-5-sonnet-20241022"
    llm.temperature = 1.0
    return llm


@pytest.fixture
def mock_google_llm():
    """Fixture providing a mock Google LLM."""
    llm = Mock()
    llm.model = "gemini-1.5-pro"
    llm.temperature = 1.0
    return llm


# ============================================================================
# Trading Graph Test Fixtures
# ============================================================================

@pytest.fixture
def mock_trading_graph():
    """Fixture providing a mock TradingAgents graph."""
    graph = Mock()

    def mock_propagate(ticker, date):
        """Mock propagate method returning sample analysis."""
        return {
            "market_report": f"Market analysis for {ticker}",
            "fundamentals_report": f"Fundamentals analysis for {ticker}",
            "news_report": f"News sentiment for {ticker}",
            "trader_investment_plan": f"Investment decision for {ticker}",
            "bull_research": "Bullish factors...",
            "bear_research": "Bearish factors...",
            "risk_assessment": "Risk analysis..."
        }, "BUY"

    graph.propagate.side_effect = mock_propagate
    return graph


# ============================================================================
# API Response Mocks
# ============================================================================

class AlpacaResponseMocks:
    """Factory for creating mock Alpaca API responses."""

    @staticmethod
    def account_response():
        """Mock Alpaca account response."""
        return {
            "account_number": "ACC123456",
            "cash": "50000.00",
            "buying_power": "200000.00",
            "portfolio_value": "75000.00",
            "equity": "75000.00",
            "last_equity": "74500.00",
            "multiplier": "4",
            "currency": "USD",
            "pattern_day_trader": False
        }

    @staticmethod
    def position_response(symbol="AAPL"):
        """Mock Alpaca position response."""
        return {
            "symbol": symbol,
            "qty": "100",
            "avg_entry_price": "150.00",
            "current_price": "155.00",
            "market_value": "15500.00",
            "unrealized_pl": "500.00",
            "unrealized_plpc": "0.0333",
            "cost_basis": "15000.00"
        }

    @staticmethod
    def order_response(order_id="order-123", symbol="AAPL", status="accepted"):
        """Mock Alpaca order response."""
        return {
            "id": order_id,
            "symbol": symbol,
            "qty": "100",
            "side": "buy",
            "type": "market",
            "time_in_force": "day",
            "status": status,
            "submitted_at": "2024-01-15T10:30:00Z",
            "filled_qty": "100" if status == "filled" else "0",
            "filled_avg_price": "150.25" if status == "filled" else None,
            "filled_at": "2024-01-15T10:30:05Z" if status == "filled" else None
        }


@pytest.fixture
def alpaca_mocks():
    """Fixture providing Alpaca response mocks."""
    return AlpacaResponseMocks


# ============================================================================
# Test Data Builders
# ============================================================================

class OrderBuilder:
    """Builder for creating test orders with fluent interface."""

    def __init__(self):
        self.symbol = "AAPL"
        self.side = OrderSide.BUY
        self.quantity = Decimal("100")
        self.order_type = OrderType.MARKET
        self.limit_price = None
        self.stop_price = None
        self.time_in_force = "day"
        self.order_id = None
        self.status = OrderStatus.PENDING

    def with_symbol(self, symbol: str):
        """Set the symbol."""
        self.symbol = symbol
        return self

    def with_side(self, side: OrderSide):
        """Set the order side."""
        self.side = side
        return self

    def with_quantity(self, quantity: Decimal):
        """Set the quantity."""
        self.quantity = quantity
        return self

    def as_market(self):
        """Set as market order."""
        self.order_type = OrderType.MARKET
        return self

    def as_limit(self, price: Decimal):
        """Set as limit order."""
        self.order_type = OrderType.LIMIT
        self.limit_price = price
        return self

    def as_stop(self, price: Decimal):
        """Set as stop order."""
        self.order_type = OrderType.STOP
        self.stop_price = price
        return self

    def with_id(self, order_id: str):
        """Set the order ID."""
        self.order_id = order_id
        return self

    def as_filled(self, price: Decimal):
        """Set as filled order."""
        self.status = OrderStatus.FILLED
        self.filled_qty = self.quantity
        self.filled_price = price
        self.filled_at = datetime.now()
        return self

    def build(self) -> BrokerOrder:
        """Build the order."""
        order = BrokerOrder(
            symbol=self.symbol,
            side=self.side,
            quantity=self.quantity,
            order_type=self.order_type,
            limit_price=self.limit_price,
            stop_price=self.stop_price,
            time_in_force=self.time_in_force,
            order_id=self.order_id,
            status=self.status
        )

        if hasattr(self, 'filled_qty'):
            order.filled_qty = self.filled_qty
            order.filled_price = self.filled_price
            order.filled_at = self.filled_at

        return order


@pytest.fixture
def order_builder():
    """Fixture providing OrderBuilder."""
    return OrderBuilder


# ============================================================================
# Pytest Configuration
# ============================================================================

def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests"
    )
    config.addinivalue_line(
        "markers", "broker: marks tests related to broker integration"
    )
    config.addinivalue_line(
        "markers", "llm: marks tests related to LLM factory"
    )
    config.addinivalue_line(
        "markers", "web: marks tests related to web interface"
    )


# ============================================================================
# Assertion Helpers
# ============================================================================

class BrokerAssertions:
    """Helper class for broker-related assertions."""

    @staticmethod
    def assert_valid_account(account: BrokerAccount):
        """Assert that an account object is valid."""
        assert account is not None
        assert account.account_number is not None
        assert account.cash >= 0
        assert account.buying_power >= 0
        assert account.portfolio_value >= 0
        assert account.equity >= 0

    @staticmethod
    def assert_valid_position(position: BrokerPosition):
        """Assert that a position object is valid."""
        assert position is not None
        assert position.symbol is not None
        assert position.quantity != 0
        assert position.avg_entry_price > 0
        assert position.current_price > 0
        assert position.cost_basis > 0

    @staticmethod
    def assert_valid_order(order: BrokerOrder):
        """Assert that an order object is valid."""
        assert order is not None
        assert order.symbol is not None
        assert order.quantity > 0
        assert order.side in [OrderSide.BUY, OrderSide.SELL]
        assert order.order_type in [OrderType.MARKET, OrderType.LIMIT, OrderType.STOP, OrderType.STOP_LIMIT]


@pytest.fixture
def broker_assertions():
    """Fixture providing BrokerAssertions helper."""
    return BrokerAssertions
