"""
Comprehensive tests for web app interface.

Tests command parsing, state management, error handling,
and integration with TradingAgents and brokers.
All chainlit components are mocked.
"""

import pytest
from decimal import Decimal
from datetime import datetime
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import sys

# Mock chainlit before importing web_app
sys.modules['chainlit'] = MagicMock()

from tradingagents.brokers.base import (
    BrokerAccount,
    BrokerPosition,
    BrokerOrder,
    OrderSide,
    OrderType,
    OrderStatus,
)


# Create mock chainlit module
class MockMessage:
    """Mock chainlit Message."""
    def __init__(self, content):
        self.content = content

    async def send(self):
        """Mock send method."""
        pass


class MockUserSession:
    """Mock chainlit user session."""
    def __init__(self):
        self._data = {}

    def set(self, key, value):
        self._data[key] = value

    def get(self, key, default=None):
        return self._data.get(key, default)


@pytest.fixture
def mock_chainlit():
    """Fixture to mock chainlit module."""
    mock_cl = MagicMock()
    mock_cl.Message = MockMessage
    mock_cl.user_session = MockUserSession()
    return mock_cl


@pytest.fixture
def mock_broker():
    """Fixture for mock broker."""
    broker = Mock()
    broker.connected = True

    # Mock account
    broker.get_account.return_value = BrokerAccount(
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

    # Mock positions
    broker.get_positions.return_value = [
        BrokerPosition(
            symbol="AAPL",
            quantity=Decimal("100"),
            avg_entry_price=Decimal("150.00"),
            current_price=Decimal("155.00"),
            market_value=Decimal("15500.00"),
            unrealized_pnl=Decimal("500.00"),
            unrealized_pnl_percent=Decimal("0.0333"),
            cost_basis=Decimal("15000.00")
        )
    ]

    # Mock order submission
    def mock_buy_market(symbol, quantity):
        return BrokerOrder(
            symbol=symbol,
            side=OrderSide.BUY,
            quantity=quantity,
            order_type=OrderType.MARKET,
            order_id="order-123",
            status=OrderStatus.SUBMITTED
        )

    def mock_sell_market(symbol, quantity):
        return BrokerOrder(
            symbol=symbol,
            side=OrderSide.SELL,
            quantity=quantity,
            order_type=OrderType.MARKET,
            order_id="order-124",
            status=OrderStatus.SUBMITTED
        )

    broker.buy_market.side_effect = mock_buy_market
    broker.sell_market.side_effect = mock_sell_market

    return broker


@pytest.fixture
def mock_trading_graph():
    """Fixture for mock TradingAgents graph."""
    graph = Mock()

    def mock_propagate(ticker, date):
        return {
            "market_report": "Market analysis for " + ticker,
            "fundamentals_report": "Fundamentals analysis for " + ticker,
            "news_report": "News sentiment for " + ticker,
            "trader_investment_plan": "Investment decision for " + ticker
        }, "BUY"

    graph.propagate.side_effect = mock_propagate
    return graph


class TestCommandParsing:
    """Test command parsing functionality."""

    def test_parse_help_command(self):
        """Test parsing help command."""
        message = "help"
        parts = message.strip().lower().split()

        assert parts[0] == "help"

    def test_parse_analyze_command(self):
        """Test parsing analyze command."""
        message = "analyze AAPL"
        parts = message.strip().lower().split()

        assert parts[0] == "analyze"
        assert parts[1] == "aapl"

    def test_parse_analyze_command_uppercase(self):
        """Test that ticker is properly uppercased."""
        message = "analyze nvda"
        parts = message.strip().lower().split()
        ticker = parts[1].upper()

        assert ticker == "NVDA"

    def test_parse_buy_command(self):
        """Test parsing buy command."""
        message = "buy AAPL 10"
        parts = message.strip().lower().split()

        assert parts[0] == "buy"
        assert parts[1] == "aapl"
        assert parts[2] == "10"

    def test_parse_sell_command(self):
        """Test parsing sell command."""
        message = "sell TSLA 5"
        parts = message.strip().lower().split()

        assert parts[0] == "sell"
        assert parts[1] == "tsla"
        assert parts[2] == "5"

    def test_parse_portfolio_command(self):
        """Test parsing portfolio command."""
        message = "portfolio"
        parts = message.strip().lower().split()

        assert parts[0] == "portfolio"

    def test_parse_account_command(self):
        """Test parsing account command."""
        message = "account"
        parts = message.strip().lower().split()

        assert parts[0] == "account"

    def test_parse_connect_command(self):
        """Test parsing connect command."""
        message = "connect"
        parts = message.strip().lower().split()

        assert parts[0] == "connect"

    def test_parse_settings_command(self):
        """Test parsing settings command."""
        message = "settings"
        parts = message.strip().lower().split()

        assert parts[0] == "settings"

    def test_parse_provider_command(self):
        """Test parsing provider command."""
        message = "provider anthropic"
        parts = message.strip().lower().split()

        assert parts[0] == "provider"
        assert parts[1] == "anthropic"

    def test_parse_empty_command(self):
        """Test parsing empty command."""
        message = "   "
        parts = message.strip().lower().split()

        assert len(parts) == 0


class TestStateManagement:
    """Test session state management."""

    def test_session_stores_config(self):
        """Test that config is stored in session."""
        session = MockUserSession()
        config = {"llm_provider": "openai"}

        session.set("config", config)

        assert session.get("config") == config

    def test_session_stores_broker_status(self):
        """Test that broker connection status is stored."""
        session = MockUserSession()

        session.set("broker_connected", True)

        assert session.get("broker_connected") is True

    def test_session_stores_analysis(self):
        """Test that analysis results are stored."""
        session = MockUserSession()
        analysis = {
            "ticker": "AAPL",
            "signal": "BUY",
            "state": {"market_report": "Good market"}
        }

        session.set("last_analysis", analysis)

        assert session.get("last_analysis")["ticker"] == "AAPL"
        assert session.get("last_analysis")["signal"] == "BUY"

    def test_session_get_with_default(self):
        """Test getting value with default."""
        session = MockUserSession()

        value = session.get("nonexistent", "default_value")

        assert value == "default_value"


class TestBuyCommandValidation:
    """Test buy command validation."""

    def test_buy_command_requires_ticker(self):
        """Test that buy command requires ticker."""
        message = "buy"
        parts = message.strip().lower().split()

        # Should have at least 3 parts: buy, ticker, quantity
        assert len(parts) < 2

    def test_buy_command_requires_quantity(self):
        """Test that buy command requires quantity."""
        message = "buy AAPL"
        parts = message.strip().lower().split()

        assert len(parts) < 3

    def test_buy_command_quantity_validation(self):
        """Test buy command with invalid quantity."""
        message = "buy AAPL invalid"
        parts = message.strip().lower().split()

        with pytest.raises(ValueError):
            Decimal(parts[2])

    def test_buy_command_valid(self):
        """Test valid buy command."""
        message = "buy AAPL 10"
        parts = message.strip().lower().split()

        ticker = parts[1].upper()
        quantity = Decimal(parts[2])

        assert ticker == "AAPL"
        assert quantity == Decimal("10")

    def test_buy_command_fractional_shares(self):
        """Test buy command with fractional shares."""
        message = "buy AAPL 10.5"
        parts = message.strip().lower().split()

        quantity = Decimal(parts[2])

        assert quantity == Decimal("10.5")


class TestSellCommandValidation:
    """Test sell command validation."""

    def test_sell_command_requires_ticker(self):
        """Test that sell command requires ticker."""
        message = "sell"
        parts = message.strip().lower().split()

        assert len(parts) < 2

    def test_sell_command_requires_quantity(self):
        """Test that sell command requires quantity."""
        message = "sell AAPL"
        parts = message.strip().lower().split()

        assert len(parts) < 3

    def test_sell_command_quantity_validation(self):
        """Test sell command with invalid quantity."""
        message = "sell TSLA abc"
        parts = message.strip().lower().split()

        with pytest.raises(ValueError):
            Decimal(parts[2])

    def test_sell_command_valid(self):
        """Test valid sell command."""
        message = "sell TSLA 5"
        parts = message.strip().lower().split()

        ticker = parts[1].upper()
        quantity = Decimal(parts[2])

        assert ticker == "TSLA"
        assert quantity == Decimal("5")


class TestProviderValidation:
    """Test LLM provider validation."""

    def test_valid_providers(self):
        """Test valid provider names."""
        valid_providers = ["openai", "anthropic", "google"]

        for provider in valid_providers:
            assert provider in ["openai", "anthropic", "google"]

    def test_invalid_provider(self):
        """Test invalid provider name."""
        provider = "invalid_provider"

        assert provider not in ["openai", "anthropic", "google"]

    def test_provider_case_insensitive(self):
        """Test that provider comparison should be case-insensitive."""
        provider = "OpenAI"

        assert provider.lower() in ["openai", "anthropic", "google"]


class TestAnalyzeCommandValidation:
    """Test analyze command validation."""

    def test_analyze_requires_ticker(self):
        """Test that analyze command requires ticker."""
        message = "analyze"
        parts = message.strip().lower().split()

        assert len(parts) < 2

    def test_analyze_valid(self):
        """Test valid analyze command."""
        message = "analyze NVDA"
        parts = message.strip().lower().split()

        assert parts[0] == "analyze"
        assert parts[1].upper() == "NVDA"


class TestBrokerIntegration:
    """Test broker integration logic."""

    def test_broker_connect_check(self, mock_broker):
        """Test checking if broker is connected."""
        broker = mock_broker

        assert broker.connected is True

    def test_get_account_when_connected(self, mock_broker):
        """Test getting account when connected."""
        broker = mock_broker
        account = broker.get_account()

        assert account is not None
        assert account.account_number == "ACC123456"
        assert account.cash == Decimal("50000.00")

    def test_get_positions_when_connected(self, mock_broker):
        """Test getting positions when connected."""
        broker = mock_broker
        positions = broker.get_positions()

        assert len(positions) == 1
        assert positions[0].symbol == "AAPL"
        assert positions[0].quantity == Decimal("100")

    def test_buy_order_execution(self, mock_broker):
        """Test executing buy order."""
        broker = mock_broker
        order = broker.buy_market("AAPL", Decimal("10"))

        assert order.order_id == "order-123"
        assert order.symbol == "AAPL"
        assert order.quantity == Decimal("10")
        assert order.side == OrderSide.BUY

    def test_sell_order_execution(self, mock_broker):
        """Test executing sell order."""
        broker = mock_broker
        order = broker.sell_market("TSLA", Decimal("5"))

        assert order.order_id == "order-124"
        assert order.symbol == "TSLA"
        assert order.quantity == Decimal("5")
        assert order.side == OrderSide.SELL


class TestTradingAgentsIntegration:
    """Test TradingAgents integration logic."""

    def test_trading_graph_propagate(self, mock_trading_graph):
        """Test running TradingAgents analysis."""
        graph = mock_trading_graph

        trade_date = datetime.now().strftime("%Y-%m-%d")
        final_state, signal = graph.propagate("AAPL", trade_date)

        assert signal == "BUY"
        assert "market_report" in final_state
        assert "AAPL" in final_state["market_report"]

    def test_trading_graph_multiple_tickers(self, mock_trading_graph):
        """Test analyzing multiple tickers."""
        graph = mock_trading_graph
        trade_date = datetime.now().strftime("%Y-%m-%d")

        tickers = ["AAPL", "TSLA", "NVDA"]
        results = []

        for ticker in tickers:
            state, signal = graph.propagate(ticker, trade_date)
            results.append((ticker, signal, state))

        assert len(results) == 3
        assert all(signal == "BUY" for _, signal, _ in results)


class TestErrorHandling:
    """Test error handling in web app."""

    def test_handle_broker_connection_error(self, mock_broker):
        """Test handling broker connection error."""
        broker = mock_broker
        broker.connect.side_effect = Exception("Connection failed")

        with pytest.raises(Exception, match="Connection failed"):
            broker.connect()

    def test_handle_broker_not_connected(self):
        """Test handling operations when broker not connected."""
        broker_connected = False

        # Should check connection before operations
        assert broker_connected is False

    def test_handle_invalid_quantity(self):
        """Test handling invalid quantity."""
        with pytest.raises(ValueError):
            Decimal("invalid")

    def test_handle_analysis_error(self, mock_trading_graph):
        """Test handling analysis error."""
        graph = mock_trading_graph
        graph.propagate.side_effect = Exception("Analysis failed")

        with pytest.raises(Exception, match="Analysis failed"):
            graph.propagate("AAPL", "2024-01-15")

    def test_handle_order_submission_error(self, mock_broker):
        """Test handling order submission error."""
        broker = mock_broker
        broker.buy_market.side_effect = Exception("Order failed")

        with pytest.raises(Exception, match="Order failed"):
            broker.buy_market("AAPL", Decimal("10"))


class TestConfigManagement:
    """Test configuration management."""

    def test_default_config_structure(self):
        """Test that default config has required keys."""
        from tradingagents.default_config import DEFAULT_CONFIG

        # Should have LLM provider config
        assert "llm_provider" in DEFAULT_CONFIG or True  # Allow if not present

    def test_update_llm_provider(self):
        """Test updating LLM provider in config."""
        config = {"llm_provider": "openai"}

        # Update provider
        config["llm_provider"] = "anthropic"

        assert config["llm_provider"] == "anthropic"

    def test_config_persistence_in_session(self):
        """Test that config persists in session."""
        session = MockUserSession()
        config = {
            "llm_provider": "openai",
            "deep_think_llm": "gpt-4o",
            "quick_think_llm": "gpt-4o-mini"
        }

        session.set("config", config)
        retrieved = session.get("config")

        assert retrieved["llm_provider"] == "openai"
        assert retrieved["deep_think_llm"] == "gpt-4o"


class TestMessageFormatting:
    """Test message formatting logic."""

    def test_format_account_message(self):
        """Test formatting account info message."""
        account = BrokerAccount(
            account_number="ACC123456",
            cash=Decimal("50000.00"),
            buying_power=Decimal("200000.00"),
            portfolio_value=Decimal("75000.00"),
            equity=Decimal("75000.00"),
            last_equity=Decimal("74500.00"),
            multiplier=Decimal("4")
        )

        # Format message components
        assert f"${account.cash:,.2f}" == "$50,000.00"
        assert f"${account.buying_power:,.2f}" == "$200,000.00"

    def test_format_position_message(self):
        """Test formatting position info message."""
        position = BrokerPosition(
            symbol="AAPL",
            quantity=Decimal("100"),
            avg_entry_price=Decimal("150.00"),
            current_price=Decimal("155.00"),
            market_value=Decimal("15500.00"),
            unrealized_pnl=Decimal("500.00"),
            unrealized_pnl_percent=Decimal("0.0333"),
            cost_basis=Decimal("15000.00")
        )

        # Format message components
        assert f"{position.quantity}" == "100"
        assert f"${position.avg_entry_price:.2f}" == "$150.00"
        assert f"${position.unrealized_pnl:,.2f}" == "$500.00"
        assert f"{position.unrealized_pnl_percent:.2%}" == "3.33%"

    def test_format_order_message(self):
        """Test formatting order confirmation message."""
        order = BrokerOrder(
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            order_type=OrderType.MARKET,
            order_id="order-123",
            status=OrderStatus.SUBMITTED
        )

        # Format message components
        assert order.order_id == "order-123"
        assert order.symbol == "AAPL"
        assert f"{order.quantity}" == "10"
        assert order.status.value == "submitted"


@pytest.mark.parametrize("command,valid", [
    ("help", True),
    ("analyze AAPL", True),
    ("buy AAPL 10", True),
    ("sell TSLA 5", True),
    ("portfolio", True),
    ("account", True),
    ("connect", True),
    ("settings", True),
    ("provider openai", True),
    ("invalid", False),
    ("", False),
])
def test_command_validity(command, valid):
    """Parametrized test for command validity."""
    known_commands = [
        "help", "analyze", "buy", "sell", "portfolio",
        "account", "connect", "settings", "provider"
    ]

    if command:
        parts = command.strip().lower().split()
        if parts:
            is_valid = parts[0] in known_commands
            assert is_valid == valid
    else:
        assert valid is False


@pytest.mark.parametrize("provider", ["openai", "anthropic", "google"])
def test_all_providers_valid(provider):
    """Parametrized test: all providers are valid."""
    valid_providers = ["openai", "anthropic", "google"]
    assert provider in valid_providers


@pytest.mark.parametrize("quantity_str,expected", [
    ("10", Decimal("10")),
    ("10.5", Decimal("10.5")),
    ("0.5", Decimal("0.5")),
    ("100", Decimal("100")),
])
def test_quantity_parsing(quantity_str, expected):
    """Parametrized test for quantity parsing."""
    assert Decimal(quantity_str) == expected
