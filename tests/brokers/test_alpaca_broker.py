"""
Comprehensive tests for Alpaca broker integration.

All external API calls are mocked to ensure fast, reliable tests
without requiring actual Alpaca credentials or network access.
"""

import os
import pytest
from decimal import Decimal
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
import requests

from tradingagents.brokers.alpaca_broker import AlpacaBroker
from tradingagents.brokers.base import (
    BrokerOrder,
    BrokerPosition,
    BrokerAccount,
    OrderSide,
    OrderType,
    OrderStatus,
    BrokerError,
    ConnectionError,
    OrderError,
    InsufficientFundsError,
)


class TestAlpacaBrokerInitialization:
    """Test Alpaca broker initialization."""

    def test_init_with_credentials(self):
        """Test initialization with explicit credentials."""
        broker = AlpacaBroker(
            api_key="test-key",
            secret_key="test-secret",
            paper_trading=True
        )

        assert broker.api_key == "test-key"
        assert broker.secret_key == "test-secret"
        assert broker.paper_trading is True
        assert broker.base_url == AlpacaBroker.PAPER_BASE_URL
        assert not broker.connected

    def test_init_with_env_vars(self):
        """Test initialization with environment variables."""
        with patch.dict(os.environ, {
            "ALPACA_API_KEY": "env-key",
            "ALPACA_SECRET_KEY": "env-secret"
        }):
            broker = AlpacaBroker(paper_trading=True)

            assert broker.api_key == "env-key"
            assert broker.secret_key == "env-secret"

    def test_init_missing_credentials(self):
        """Test that missing credentials raises ValueError."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="Alpaca API credentials"):
                AlpacaBroker()

    def test_init_paper_trading_url(self):
        """Test that paper trading uses correct URL."""
        broker = AlpacaBroker(
            api_key="key",
            secret_key="secret",
            paper_trading=True
        )

        assert broker.base_url == AlpacaBroker.PAPER_BASE_URL

    def test_init_live_trading_url(self):
        """Test that live trading uses correct URL."""
        broker = AlpacaBroker(
            api_key="key",
            secret_key="secret",
            paper_trading=False
        )

        assert broker.base_url == AlpacaBroker.LIVE_BASE_URL

    def test_headers_set_correctly(self):
        """Test that API headers are set correctly."""
        broker = AlpacaBroker(
            api_key="test-key",
            secret_key="test-secret"
        )

        assert broker.headers["APCA-API-KEY-ID"] == "test-key"
        assert broker.headers["APCA-API-SECRET-KEY"] == "test-secret"


class TestAlpacaBrokerConnection:
    """Test Alpaca broker connection management."""

    @patch("tradingagents.brokers.alpaca_broker.requests.get")
    def test_connect_success(self, mock_get):
        """Test successful connection."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        broker = AlpacaBroker(api_key="key", secret_key="secret")
        result = broker.connect()

        assert result is True
        assert broker.connected is True
        mock_get.assert_called_once()

    @patch("tradingagents.brokers.alpaca_broker.requests.get")
    def test_connect_invalid_credentials(self, mock_get):
        """Test connection with invalid credentials."""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_get.return_value = mock_response

        broker = AlpacaBroker(api_key="bad-key", secret_key="bad-secret")

        with pytest.raises(ConnectionError, match="Invalid API credentials"):
            broker.connect()

    @patch("tradingagents.brokers.alpaca_broker.requests.get")
    def test_connect_network_error(self, mock_get):
        """Test connection with network error."""
        mock_get.side_effect = requests.exceptions.RequestException("Network error")

        broker = AlpacaBroker(api_key="key", secret_key="secret")

        with pytest.raises(ConnectionError, match="Failed to connect"):
            broker.connect()

    @patch("tradingagents.brokers.alpaca_broker.requests.get")
    def test_connect_other_error(self, mock_get):
        """Test connection with other HTTP error."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal server error"
        mock_get.return_value = mock_response

        broker = AlpacaBroker(api_key="key", secret_key="secret")

        with pytest.raises(ConnectionError, match="Connection failed"):
            broker.connect()

    def test_disconnect(self):
        """Test disconnection."""
        broker = AlpacaBroker(api_key="key", secret_key="secret")
        broker.connected = True

        broker.disconnect()

        assert broker.connected is False


class TestAlpacaBrokerAccount:
    """Test Alpaca broker account operations."""

    @patch("tradingagents.brokers.alpaca_broker.requests.get")
    def test_get_account_success(self, mock_get):
        """Test successful account retrieval."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
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
        mock_get.return_value = mock_response

        broker = AlpacaBroker(api_key="key", secret_key="secret")
        broker.connected = True

        account = broker.get_account()

        assert isinstance(account, BrokerAccount)
        assert account.account_number == "ACC123456"
        assert account.cash == Decimal("50000.00")
        assert account.buying_power == Decimal("200000.00")
        assert account.portfolio_value == Decimal("75000.00")
        assert account.currency == "USD"

    def test_get_account_not_connected(self):
        """Test get_account when not connected."""
        broker = AlpacaBroker(api_key="key", secret_key="secret")

        with pytest.raises(BrokerError, match="Not connected"):
            broker.get_account()

    @patch("tradingagents.brokers.alpaca_broker.requests.get")
    def test_get_account_network_error(self, mock_get):
        """Test get_account with network error."""
        mock_get.side_effect = requests.exceptions.RequestException("Network error")

        broker = AlpacaBroker(api_key="key", secret_key="secret")
        broker.connected = True

        with pytest.raises(BrokerError, match="Failed to get account"):
            broker.get_account()


class TestAlpacaBrokerPositions:
    """Test Alpaca broker position operations."""

    @patch("tradingagents.brokers.alpaca_broker.requests.get")
    def test_get_positions_success(self, mock_get):
        """Test successful positions retrieval."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "symbol": "AAPL",
                "qty": "100",
                "avg_entry_price": "150.00",
                "current_price": "155.00",
                "market_value": "15500.00",
                "unrealized_pl": "500.00",
                "unrealized_plpc": "0.0333",
                "cost_basis": "15000.00"
            },
            {
                "symbol": "TSLA",
                "qty": "50",
                "avg_entry_price": "250.00",
                "current_price": "240.00",
                "market_value": "12000.00",
                "unrealized_pl": "-500.00",
                "unrealized_plpc": "-0.04",
                "cost_basis": "12500.00"
            }
        ]
        mock_get.return_value = mock_response

        broker = AlpacaBroker(api_key="key", secret_key="secret")
        broker.connected = True

        positions = broker.get_positions()

        assert len(positions) == 2
        assert positions[0].symbol == "AAPL"
        assert positions[0].quantity == Decimal("100")
        assert positions[1].symbol == "TSLA"
        assert positions[1].unrealized_pnl == Decimal("-500.00")

    @patch("tradingagents.brokers.alpaca_broker.requests.get")
    def test_get_positions_empty(self, mock_get):
        """Test get_positions with no positions."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_get.return_value = mock_response

        broker = AlpacaBroker(api_key="key", secret_key="secret")
        broker.connected = True

        positions = broker.get_positions()

        assert positions == []

    def test_get_positions_not_connected(self):
        """Test get_positions when not connected."""
        broker = AlpacaBroker(api_key="key", secret_key="secret")

        with pytest.raises(BrokerError, match="Not connected"):
            broker.get_positions()

    @patch("tradingagents.brokers.alpaca_broker.requests.get")
    def test_get_position_success(self, mock_get):
        """Test successful single position retrieval."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "symbol": "AAPL",
            "qty": "100",
            "avg_entry_price": "150.00",
            "current_price": "155.00",
            "market_value": "15500.00",
            "unrealized_pl": "500.00",
            "unrealized_plpc": "0.0333",
            "cost_basis": "15000.00"
        }
        mock_get.return_value = mock_response

        broker = AlpacaBroker(api_key="key", secret_key="secret")
        broker.connected = True

        position = broker.get_position("AAPL")

        assert position is not None
        assert position.symbol == "AAPL"
        assert position.quantity == Decimal("100")

    @patch("tradingagents.brokers.alpaca_broker.requests.get")
    def test_get_position_not_found(self, mock_get):
        """Test get_position for non-existent position."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        broker = AlpacaBroker(api_key="key", secret_key="secret")
        broker.connected = True

        position = broker.get_position("AAPL")

        assert position is None


class TestAlpacaBrokerOrders:
    """Test Alpaca broker order operations."""

    @patch("tradingagents.brokers.alpaca_broker.requests.post")
    def test_submit_market_order_success(self, mock_post):
        """Test successful market order submission."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "order-123",
            "symbol": "AAPL",
            "qty": "100",
            "side": "buy",
            "type": "market",
            "time_in_force": "day",
            "status": "accepted",
            "submitted_at": "2024-01-15T10:30:00Z",
            "filled_qty": "0",
        }
        mock_post.return_value = mock_response

        broker = AlpacaBroker(api_key="key", secret_key="secret")
        broker.connected = True

        order = BrokerOrder(
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=Decimal("100"),
            order_type=OrderType.MARKET
        )

        result = broker.submit_order(order)

        assert result.order_id == "order-123"
        assert result.status == OrderStatus.SUBMITTED
        assert result.submitted_at is not None

    @patch("tradingagents.brokers.alpaca_broker.requests.post")
    def test_submit_limit_order_success(self, mock_post):
        """Test successful limit order submission."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "order-124",
            "symbol": "TSLA",
            "qty": "50",
            "side": "sell",
            "type": "limit",
            "limit_price": "250.50",
            "time_in_force": "gtc",
            "status": "accepted",
            "submitted_at": "2024-01-15T10:30:00Z",
            "filled_qty": "0",
        }
        mock_post.return_value = mock_response

        broker = AlpacaBroker(api_key="key", secret_key="secret")
        broker.connected = True

        order = BrokerOrder(
            symbol="TSLA",
            side=OrderSide.SELL,
            quantity=Decimal("50"),
            order_type=OrderType.LIMIT,
            limit_price=Decimal("250.50"),
            time_in_force="gtc"
        )

        result = broker.submit_order(order)

        assert result.order_id == "order-124"

    @patch("tradingagents.brokers.alpaca_broker.requests.post")
    def test_submit_stop_order_success(self, mock_post):
        """Test successful stop order submission."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "order-125",
            "symbol": "NVDA",
            "qty": "25",
            "side": "sell",
            "type": "stop",
            "stop_price": "800.00",
            "time_in_force": "day",
            "status": "accepted",
            "submitted_at": "2024-01-15T10:30:00Z",
            "filled_qty": "0",
        }
        mock_post.return_value = mock_response

        broker = AlpacaBroker(api_key="key", secret_key="secret")
        broker.connected = True

        order = BrokerOrder(
            symbol="NVDA",
            side=OrderSide.SELL,
            quantity=Decimal("25"),
            order_type=OrderType.STOP,
            stop_price=Decimal("800.00")
        )

        result = broker.submit_order(order)

        assert result.order_id == "order-125"

    @patch("tradingagents.brokers.alpaca_broker.requests.post")
    def test_submit_order_insufficient_funds(self, mock_post):
        """Test order submission with insufficient funds."""
        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.json.return_value = {
            "message": "Insufficient buying power"
        }
        mock_post.return_value = mock_response

        broker = AlpacaBroker(api_key="key", secret_key="secret")
        broker.connected = True

        order = BrokerOrder(
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=Decimal("1000000"),
            order_type=OrderType.MARKET
        )

        with pytest.raises(InsufficientFundsError):
            broker.submit_order(order)

    def test_submit_order_not_connected(self):
        """Test submit_order when not connected."""
        broker = AlpacaBroker(api_key="key", secret_key="secret")

        order = BrokerOrder(
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=Decimal("100"),
            order_type=OrderType.MARKET
        )

        with pytest.raises(BrokerError, match="Not connected"):
            broker.submit_order(order)

    def test_submit_limit_order_missing_price(self):
        """Test limit order without limit_price raises error."""
        broker = AlpacaBroker(api_key="key", secret_key="secret")
        broker.connected = True

        order = BrokerOrder(
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=Decimal("100"),
            order_type=OrderType.LIMIT
            # Missing limit_price
        )

        with pytest.raises(OrderError, match="Limit price required"):
            broker.submit_order(order)

    def test_submit_stop_order_missing_price(self):
        """Test stop order without stop_price raises error."""
        broker = AlpacaBroker(api_key="key", secret_key="secret")
        broker.connected = True

        order = BrokerOrder(
            symbol="AAPL",
            side=OrderSide.SELL,
            quantity=Decimal("100"),
            order_type=OrderType.STOP
            # Missing stop_price
        )

        with pytest.raises(OrderError, match="Stop price required"):
            broker.submit_order(order)

    @patch("tradingagents.brokers.alpaca_broker.requests.delete")
    def test_cancel_order_success(self, mock_delete):
        """Test successful order cancellation."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_delete.return_value = mock_response

        broker = AlpacaBroker(api_key="key", secret_key="secret")
        broker.connected = True

        result = broker.cancel_order("order-123")

        assert result is True

    @patch("tradingagents.brokers.alpaca_broker.requests.delete")
    def test_cancel_order_not_found(self, mock_delete):
        """Test cancelling non-existent order."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_delete.return_value = mock_response

        broker = AlpacaBroker(api_key="key", secret_key="secret")
        broker.connected = True

        with pytest.raises(OrderError, match="not found"):
            broker.cancel_order("order-999")

    @patch("tradingagents.brokers.alpaca_broker.requests.get")
    def test_get_order_success(self, mock_get):
        """Test successful order retrieval."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "order-123",
            "symbol": "AAPL",
            "qty": "100",
            "side": "buy",
            "type": "market",
            "time_in_force": "day",
            "status": "filled",
            "submitted_at": "2024-01-15T10:30:00Z",
            "filled_at": "2024-01-15T10:30:05Z",
            "filled_qty": "100",
            "filled_avg_price": "150.25"
        }
        mock_get.return_value = mock_response

        broker = AlpacaBroker(api_key="key", secret_key="secret")
        broker.connected = True

        order = broker.get_order("order-123")

        assert order is not None
        assert order.order_id == "order-123"
        assert order.status == OrderStatus.FILLED
        assert order.filled_qty == Decimal("100")
        assert order.filled_price == Decimal("150.25")

    @patch("tradingagents.brokers.alpaca_broker.requests.get")
    def test_get_order_not_found(self, mock_get):
        """Test get_order for non-existent order."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        broker = AlpacaBroker(api_key="key", secret_key="secret")
        broker.connected = True

        order = broker.get_order("order-999")

        assert order is None

    @patch("tradingagents.brokers.alpaca_broker.requests.get")
    def test_get_orders_all(self, mock_get):
        """Test getting all orders."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "id": "order-1",
                "symbol": "AAPL",
                "qty": "100",
                "side": "buy",
                "type": "market",
                "time_in_force": "day",
                "status": "filled",
                "submitted_at": "2024-01-15T10:30:00Z",
                "filled_qty": "100"
            },
            {
                "id": "order-2",
                "symbol": "TSLA",
                "qty": "50",
                "side": "sell",
                "type": "limit",
                "limit_price": "250.00",
                "time_in_force": "gtc",
                "status": "accepted",
                "submitted_at": "2024-01-15T11:00:00Z",
                "filled_qty": "0"
            }
        ]
        mock_get.return_value = mock_response

        broker = AlpacaBroker(api_key="key", secret_key="secret")
        broker.connected = True

        orders = broker.get_orders()

        assert len(orders) == 2
        assert orders[0].order_id == "order-1"
        assert orders[1].order_id == "order-2"

    @patch("tradingagents.brokers.alpaca_broker.requests.get")
    def test_get_orders_filtered(self, mock_get):
        """Test getting orders with status filter."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_get.return_value = mock_response

        broker = AlpacaBroker(api_key="key", secret_key="secret")
        broker.connected = True

        orders = broker.get_orders(status=OrderStatus.FILLED, limit=10)

        # Verify the call was made with correct parameters
        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args[1]
        assert "params" in call_kwargs
        assert call_kwargs["params"]["limit"] == 10


class TestAlpacaBrokerPricing:
    """Test Alpaca broker pricing operations."""

    @patch("tradingagents.brokers.alpaca_broker.requests.get")
    def test_get_current_price_success(self, mock_get):
        """Test successful price retrieval."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "trade": {
                "p": 155.50,
                "s": 100,
                "t": "2024-01-15T10:30:00Z"
            }
        }
        mock_get.return_value = mock_response

        broker = AlpacaBroker(api_key="key", secret_key="secret")
        broker.connected = True

        price = broker.get_current_price("AAPL")

        assert price == Decimal("155.50")

    def test_get_current_price_not_connected(self):
        """Test get_current_price when not connected."""
        broker = AlpacaBroker(api_key="key", secret_key="secret")

        with pytest.raises(BrokerError, match="Not connected"):
            broker.get_current_price("AAPL")

    @patch("tradingagents.brokers.alpaca_broker.requests.get")
    def test_get_current_price_network_error(self, mock_get):
        """Test get_current_price with network error."""
        mock_get.side_effect = requests.exceptions.RequestException("Network error")

        broker = AlpacaBroker(api_key="key", secret_key="secret")
        broker.connected = True

        with pytest.raises(BrokerError, match="Failed to get price"):
            broker.get_current_price("AAPL")


class TestAlpacaBrokerHelperMethods:
    """Test Alpaca broker helper methods."""

    def test_convert_order_type(self):
        """Test order type conversion."""
        broker = AlpacaBroker(api_key="key", secret_key="secret")

        assert broker._convert_order_type(OrderType.MARKET) == "market"
        assert broker._convert_order_type(OrderType.LIMIT) == "limit"
        assert broker._convert_order_type(OrderType.STOP) == "stop"
        assert broker._convert_order_type(OrderType.STOP_LIMIT) == "stop_limit"

    def test_convert_order_status(self):
        """Test order status conversion from Alpaca."""
        broker = AlpacaBroker(api_key="key", secret_key="secret")

        assert broker._convert_order_status("new") == OrderStatus.SUBMITTED
        assert broker._convert_order_status("accepted") == OrderStatus.SUBMITTED
        assert broker._convert_order_status("filled") == OrderStatus.FILLED
        assert broker._convert_order_status("partially_filled") == OrderStatus.PARTIALLY_FILLED
        assert broker._convert_order_status("canceled") == OrderStatus.CANCELLED
        assert broker._convert_order_status("rejected") == OrderStatus.REJECTED
        assert broker._convert_order_status("expired") == OrderStatus.CANCELLED

    def test_convert_status_to_alpaca(self):
        """Test order status conversion to Alpaca format."""
        broker = AlpacaBroker(api_key="key", secret_key="secret")

        assert broker._convert_status_to_alpaca(OrderStatus.PENDING) == "pending"
        assert broker._convert_status_to_alpaca(OrderStatus.SUBMITTED) == "open"
        assert broker._convert_status_to_alpaca(OrderStatus.FILLED) == "filled"
        assert broker._convert_status_to_alpaca(OrderStatus.CANCELLED) == "canceled"

    def test_parse_order_type(self):
        """Test parsing order type from Alpaca."""
        broker = AlpacaBroker(api_key="key", secret_key="secret")

        assert broker._parse_order_type("market") == OrderType.MARKET
        assert broker._parse_order_type("limit") == OrderType.LIMIT
        assert broker._parse_order_type("stop") == OrderType.STOP
        assert broker._parse_order_type("stop_limit") == OrderType.STOP_LIMIT

    def test_convert_alpaca_order(self):
        """Test converting Alpaca order JSON to BrokerOrder."""
        broker = AlpacaBroker(api_key="key", secret_key="secret")

        alpaca_data = {
            "id": "order-123",
            "symbol": "AAPL",
            "qty": "100",
            "side": "buy",
            "type": "limit",
            "limit_price": "150.00",
            "time_in_force": "day",
            "status": "filled",
            "filled_qty": "100",
            "filled_avg_price": "149.75",
            "submitted_at": "2024-01-15T10:30:00Z",
            "filled_at": "2024-01-15T10:30:05Z"
        }

        order = broker._convert_alpaca_order(alpaca_data)

        assert order.order_id == "order-123"
        assert order.symbol == "AAPL"
        assert order.quantity == Decimal("100")
        assert order.side == OrderSide.BUY
        assert order.order_type == OrderType.LIMIT
        assert order.limit_price == Decimal("150.00")
        assert order.status == OrderStatus.FILLED
        assert order.filled_qty == Decimal("100")
        assert order.filled_price == Decimal("149.75")


@pytest.mark.parametrize("paper_trading,expected_url", [
    (True, AlpacaBroker.PAPER_BASE_URL),
    (False, AlpacaBroker.LIVE_BASE_URL),
])
def test_broker_url_selection(paper_trading, expected_url):
    """Parametrized test for URL selection based on paper_trading flag."""
    broker = AlpacaBroker(
        api_key="key",
        secret_key="secret",
        paper_trading=paper_trading
    )

    assert broker.base_url == expected_url


@pytest.mark.parametrize("alpaca_status,expected_status", [
    ("new", OrderStatus.SUBMITTED),
    ("accepted", OrderStatus.SUBMITTED),
    ("filled", OrderStatus.FILLED),
    ("partially_filled", OrderStatus.PARTIALLY_FILLED),
    ("canceled", OrderStatus.CANCELLED),
    ("rejected", OrderStatus.REJECTED),
])
def test_status_conversion_parametrized(alpaca_status, expected_status):
    """Parametrized test for status conversion."""
    broker = AlpacaBroker(api_key="key", secret_key="secret")
    assert broker._convert_order_status(alpaca_status) == expected_status
