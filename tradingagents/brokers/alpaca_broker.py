"""
Alpaca broker integration for paper and live trading.

Alpaca offers free paper trading accounts with real market data,
making it perfect for testing and development.

Setup:
1. Sign up at https://alpaca.markets
2. Get API keys from dashboard
3. Set ALPACA_API_KEY and ALPACA_SECRET_KEY in .env
4. Set ALPACA_PAPER_TRADING=true for paper trading
"""

import os
from decimal import Decimal
from datetime import datetime
from typing import List, Dict, Optional
import requests
from requests.auth import HTTPBasicAuth

from .base import (
    BaseBroker,
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


class AlpacaBroker(BaseBroker):
    """
    Alpaca broker integration.

    Supports both paper trading (free) and live trading.
    Paper trading provides realistic simulation with real market data.

    Example:
        >>> broker = AlpacaBroker(paper_trading=True)
        >>> broker.connect()
        >>> account = broker.get_account()
        >>> print(f"Buying power: ${account.buying_power}")
    """

    PAPER_BASE_URL = "https://paper-api.alpaca.markets"
    LIVE_BASE_URL = "https://api.alpaca.markets"
    API_VERSION = "v2"

    def __init__(
        self,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        paper_trading: bool = True,
    ):
        """
        Initialize Alpaca broker connection.

        Args:
            api_key: Alpaca API key (defaults to ALPACA_API_KEY env var)
            secret_key: Alpaca secret key (defaults to ALPACA_SECRET_KEY env var)
            paper_trading: Use paper trading (True) or live trading (False)
        """
        super().__init__(paper_trading)

        self.api_key = api_key or os.getenv("ALPACA_API_KEY")
        self.secret_key = secret_key or os.getenv("ALPACA_SECRET_KEY")

        if not self.api_key or not self.secret_key:
            raise ValueError(
                "Alpaca API credentials not found. "
                "Set ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables "
                "or pass them to the constructor."
            )

        self.base_url = self.PAPER_BASE_URL if paper_trading else self.LIVE_BASE_URL
        self.headers = {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.secret_key,
        }
        self.connected = False

    def connect(self) -> bool:
        """
        Connect to Alpaca and verify credentials.

        Returns:
            True if connection successful

        Raises:
            ConnectionError: If connection fails
        """
        try:
            # Test connection by fetching account
            response = requests.get(
                f"{self.base_url}/{self.API_VERSION}/account",
                headers=self.headers,
                timeout=10,
            )

            if response.status_code == 200:
                self.connected = True
                return True
            elif response.status_code == 401:
                raise ConnectionError("Invalid API credentials")
            else:
                raise ConnectionError(f"Connection failed: {response.text}")

        except requests.exceptions.RequestException as e:
            raise ConnectionError(f"Failed to connect to Alpaca: {e}")

    def disconnect(self) -> None:
        """Disconnect from Alpaca."""
        self.connected = False

    def get_account(self) -> BrokerAccount:
        """
        Get account information.

        Returns:
            BrokerAccount with current account details

        Raises:
            BrokerError: If request fails
        """
        if not self.connected:
            raise BrokerError("Not connected to broker")

        try:
            response = requests.get(
                f"{self.base_url}/{self.API_VERSION}/account",
                headers=self.headers,
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()

            return BrokerAccount(
                account_number=data["account_number"],
                cash=Decimal(data["cash"]),
                buying_power=Decimal(data["buying_power"]),
                portfolio_value=Decimal(data["portfolio_value"]),
                equity=Decimal(data["equity"]),
                last_equity=Decimal(data["last_equity"]),
                multiplier=Decimal(data["multiplier"]),
                currency=data["currency"],
                pattern_day_trader=data.get("pattern_day_trader", False),
            )

        except requests.exceptions.RequestException as e:
            raise BrokerError(f"Failed to get account: {e}")

    def get_positions(self) -> List[BrokerPosition]:
        """
        Get all current positions.

        Returns:
            List of BrokerPosition objects

        Raises:
            BrokerError: If request fails
        """
        if not self.connected:
            raise BrokerError("Not connected to broker")

        try:
            response = requests.get(
                f"{self.base_url}/{self.API_VERSION}/positions",
                headers=self.headers,
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()

            positions = []
            for pos in data:
                positions.append(BrokerPosition(
                    symbol=pos["symbol"],
                    quantity=Decimal(pos["qty"]),
                    avg_entry_price=Decimal(pos["avg_entry_price"]),
                    current_price=Decimal(pos["current_price"]),
                    market_value=Decimal(pos["market_value"]),
                    unrealized_pnl=Decimal(pos["unrealized_pl"]),
                    unrealized_pnl_percent=Decimal(pos["unrealized_plpc"]),
                    cost_basis=Decimal(pos["cost_basis"]),
                ))

            return positions

        except requests.exceptions.RequestException as e:
            raise BrokerError(f"Failed to get positions: {e}")

    def get_position(self, symbol: str) -> Optional[BrokerPosition]:
        """
        Get position for a specific symbol.

        Args:
            symbol: Stock ticker symbol

        Returns:
            BrokerPosition if exists, None otherwise

        Raises:
            BrokerError: If request fails
        """
        if not self.connected:
            raise BrokerError("Not connected to broker")

        try:
            response = requests.get(
                f"{self.base_url}/{self.API_VERSION}/positions/{symbol}",
                headers=self.headers,
                timeout=10,
            )

            if response.status_code == 404:
                return None

            response.raise_for_status()
            pos = response.json()

            return BrokerPosition(
                symbol=pos["symbol"],
                quantity=Decimal(pos["qty"]),
                avg_entry_price=Decimal(pos["avg_entry_price"]),
                current_price=Decimal(pos["current_price"]),
                market_value=Decimal(pos["market_value"]),
                unrealized_pnl=Decimal(pos["unrealized_pl"]),
                unrealized_pnl_percent=Decimal(pos["unrealized_plpc"]),
                cost_basis=Decimal(pos["cost_basis"]),
            )

        except requests.exceptions.RequestException as e:
            raise BrokerError(f"Failed to get position for {symbol}: {e}")

    def submit_order(self, order: BrokerOrder) -> BrokerOrder:
        """
        Submit an order to Alpaca.

        Args:
            order: BrokerOrder to submit

        Returns:
            BrokerOrder with updated status and order_id

        Raises:
            OrderError: If order submission fails
            InsufficientFundsError: If insufficient buying power
        """
        if not self.connected:
            raise BrokerError("Not connected to broker")

        # Build order payload
        payload = {
            "symbol": order.symbol,
            "qty": str(order.quantity),
            "side": order.side.value,
            "type": self._convert_order_type(order.order_type),
            "time_in_force": order.time_in_force,
        }

        # Add limit price if needed
        if order.order_type in [OrderType.LIMIT, OrderType.STOP_LIMIT]:
            if order.limit_price is None:
                raise OrderError("Limit price required for limit orders")
            payload["limit_price"] = str(order.limit_price)

        # Add stop price if needed
        if order.order_type in [OrderType.STOP, OrderType.STOP_LIMIT]:
            if order.stop_price is None:
                raise OrderError("Stop price required for stop orders")
            payload["stop_price"] = str(order.stop_price)

        try:
            response = requests.post(
                f"{self.base_url}/{self.API_VERSION}/orders",
                headers=self.headers,
                json=payload,
                timeout=10,
            )

            # Check for insufficient funds
            if response.status_code == 403:
                error_msg = response.json().get("message", "")
                if "insufficient" in error_msg.lower():
                    raise InsufficientFundsError(error_msg)

            response.raise_for_status()
            data = response.json()

            # Update order with response
            order.order_id = data["id"]
            order.status = self._convert_order_status(data["status"])
            order.submitted_at = datetime.fromisoformat(
                data["submitted_at"].replace("Z", "+00:00")
            )

            if data.get("filled_at"):
                order.filled_at = datetime.fromisoformat(
                    data["filled_at"].replace("Z", "+00:00")
                )
                order.filled_qty = Decimal(data["filled_qty"])
                if data.get("filled_avg_price"):
                    order.filled_price = Decimal(data["filled_avg_price"])

            return order

        except InsufficientFundsError:
            raise
        except requests.exceptions.RequestException as e:
            raise OrderError(f"Failed to submit order: {e}")

    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order.

        Args:
            order_id: Alpaca order ID

        Returns:
            True if cancellation successful

        Raises:
            OrderError: If cancellation fails
        """
        if not self.connected:
            raise BrokerError("Not connected to broker")

        try:
            response = requests.delete(
                f"{self.base_url}/{self.API_VERSION}/orders/{order_id}",
                headers=self.headers,
                timeout=10,
            )

            if response.status_code == 404:
                raise OrderError(f"Order {order_id} not found")

            response.raise_for_status()
            return True

        except requests.exceptions.RequestException as e:
            raise OrderError(f"Failed to cancel order: {e}")

    def get_order(self, order_id: str) -> Optional[BrokerOrder]:
        """
        Get order status.

        Args:
            order_id: Alpaca order ID

        Returns:
            BrokerOrder if found, None otherwise
        """
        if not self.connected:
            raise BrokerError("Not connected to broker")

        try:
            response = requests.get(
                f"{self.base_url}/{self.API_VERSION}/orders/{order_id}",
                headers=self.headers,
                timeout=10,
            )

            if response.status_code == 404:
                return None

            response.raise_for_status()
            data = response.json()

            return self._convert_alpaca_order(data)

        except requests.exceptions.RequestException as e:
            raise BrokerError(f"Failed to get order: {e}")

    def get_orders(
        self,
        status: Optional[OrderStatus] = None,
        limit: int = 50
    ) -> List[BrokerOrder]:
        """
        Get orders with optional filtering.

        Args:
            status: Filter by order status (None for all)
            limit: Maximum number of orders to return

        Returns:
            List of BrokerOrder objects
        """
        if not self.connected:
            raise BrokerError("Not connected to broker")

        params = {"limit": limit}
        if status:
            params["status"] = self._convert_status_to_alpaca(status)

        try:
            response = requests.get(
                f"{self.base_url}/{self.API_VERSION}/orders",
                headers=self.headers,
                params=params,
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()

            return [self._convert_alpaca_order(order) for order in data]

        except requests.exceptions.RequestException as e:
            raise BrokerError(f"Failed to get orders: {e}")

    def get_current_price(self, symbol: str) -> Decimal:
        """
        Get current market price for a symbol.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Current market price

        Raises:
            BrokerError: If price cannot be retrieved
        """
        if not self.connected:
            raise BrokerError("Not connected to broker")

        try:
            # Use latest trade endpoint
            response = requests.get(
                f"{self.base_url}/{self.API_VERSION}/stocks/{symbol}/trades/latest",
                headers=self.headers,
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()

            return Decimal(str(data["trade"]["p"]))

        except requests.exceptions.RequestException as e:
            raise BrokerError(f"Failed to get price for {symbol}: {e}")

    # Helper methods

    def _convert_order_type(self, order_type: OrderType) -> str:
        """Convert OrderType enum to Alpaca order type string."""
        mapping = {
            OrderType.MARKET: "market",
            OrderType.LIMIT: "limit",
            OrderType.STOP: "stop",
            OrderType.STOP_LIMIT: "stop_limit",
        }
        return mapping[order_type]

    def _convert_order_status(self, alpaca_status: str) -> OrderStatus:
        """Convert Alpaca order status to OrderStatus enum."""
        mapping = {
            "new": OrderStatus.SUBMITTED,
            "pending_new": OrderStatus.PENDING,
            "accepted": OrderStatus.SUBMITTED,
            "filled": OrderStatus.FILLED,
            "partially_filled": OrderStatus.PARTIALLY_FILLED,
            "canceled": OrderStatus.CANCELLED,
            "rejected": OrderStatus.REJECTED,
            "expired": OrderStatus.CANCELLED,
        }
        return mapping.get(alpaca_status, OrderStatus.PENDING)

    def _convert_status_to_alpaca(self, status: OrderStatus) -> str:
        """Convert OrderStatus enum to Alpaca status filter."""
        mapping = {
            OrderStatus.PENDING: "pending",
            OrderStatus.SUBMITTED: "open",
            OrderStatus.FILLED: "filled",
            OrderStatus.PARTIALLY_FILLED: "open",
            OrderStatus.CANCELLED: "canceled",
            OrderStatus.REJECTED: "rejected",
        }
        return mapping.get(status, "all")

    def _convert_alpaca_order(self, data: dict) -> BrokerOrder:
        """Convert Alpaca order JSON to BrokerOrder object."""
        order = BrokerOrder(
            symbol=data["symbol"],
            side=OrderSide.BUY if data["side"] == "buy" else OrderSide.SELL,
            quantity=Decimal(data["qty"]),
            order_type=self._parse_order_type(data["type"]),
            time_in_force=data["time_in_force"],
            order_id=data["id"],
            status=self._convert_order_status(data["status"]),
            filled_qty=Decimal(data.get("filled_qty", "0")),
        )

        if data.get("limit_price"):
            order.limit_price = Decimal(data["limit_price"])

        if data.get("stop_price"):
            order.stop_price = Decimal(data["stop_price"])

        if data.get("submitted_at"):
            order.submitted_at = datetime.fromisoformat(
                data["submitted_at"].replace("Z", "+00:00")
            )

        if data.get("filled_at"):
            order.filled_at = datetime.fromisoformat(
                data["filled_at"].replace("Z", "+00:00")
            )

        if data.get("filled_avg_price"):
            order.filled_price = Decimal(data["filled_avg_price"])

        return order

    def _parse_order_type(self, alpaca_type: str) -> OrderType:
        """Parse Alpaca order type string to OrderType enum."""
        mapping = {
            "market": OrderType.MARKET,
            "limit": OrderType.LIMIT,
            "stop": OrderType.STOP,
            "stop_limit": OrderType.STOP_LIMIT,
        }
        return mapping.get(alpaca_type, OrderType.MARKET)
