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
import logging
import threading
from decimal import Decimal
from datetime import datetime
from typing import List, Dict, Optional
import requests
from requests.auth import HTTPBasicAuth
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .base import (
    BaseBroker,
    BrokerOrder,
    BrokerPosition,
    BrokerAccount,
    OrderSide,
    OrderType,
    OrderStatus,
    BrokerError,
    BrokerConnectionError,
    OrderError,
    InsufficientFundsError,
)
from tradingagents.security import RateLimiter

logger = logging.getLogger(__name__)


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
    ) -> None:
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

        # Thread safety
        self._lock = threading.RLock()
        self._connected = False  # Private variable

        # Alpaca rate limit: 200 requests per minute
        # Set to 180 to leave some safety margin
        self._rate_limiter = RateLimiter(max_calls=180, period=60)

        # Create session with connection pooling and retry logic
        self._session = requests.Session()
        self._session.headers.update(self.headers)

        # Configure retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET", "POST", "DELETE"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self._session.mount("https://", adapter)

        # Configurable timeout
        self.timeout = 10

    @property
    def connected(self) -> bool:
        """Thread-safe connected status."""
        with self._lock:
            return self._connected

    @connected.setter
    def connected(self, value: bool):
        """Thread-safe connected status setter."""
        with self._lock:
            self._connected = value

    def _api_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """
        Make rate-limited API request to Alpaca.

        Args:
            method: HTTP method (GET, POST, DELETE, etc.)
            endpoint: API endpoint (without base URL)
            **kwargs: Additional arguments to pass to requests (params, json, etc.)

        Returns:
            Response object

        Raises:
            requests.exceptions.RequestException: If request fails
        """
        @self._rate_limiter
        def _make_call():
            url = f"{self.base_url}/{self.API_VERSION}/{endpoint}"
            response = self._session.request(
                method,
                url,
                timeout=self.timeout,
                **kwargs
            )
            return response

        return _make_call()

    def connect(self) -> bool:
        """
        Connect to Alpaca and verify credentials.

        This method tests the connection by fetching account information
        and caches the connection state for subsequent operations.

        Returns:
            True if connection successful

        Raises:
            BrokerConnectionError: If connection fails due to API errors or
                invalid credentials

        Performance:
            Typical execution: 100-300ms (network dependent)

        Example:
            >>> broker = AlpacaBroker(paper_trading=True)
            >>> if broker.connect():
            ...     print("Connected!")
        """
        with self._lock:
            if self._connected:
                logger.info("Already connected to Alpaca")
                return True

            trading_mode = "paper trading" if self.paper_trading else "live trading"
            logger.info("Connecting to Alpaca %s", trading_mode)

            try:
                # Test connection by fetching account
                response = self._api_request("GET", "account")

                if response.status_code == 200:
                    data = response.json()
                    account_number = data.get("account_number", "unknown")
                    self._connected = True
                    logger.info("Successfully connected to Alpaca (Account: %s)", account_number)
                    return True
                elif response.status_code == 401:
                    logger.error("Failed to connect to Alpaca: Invalid API credentials")
                    raise BrokerConnectionError("Invalid API credentials")
                else:
                    logger.error("Failed to connect to Alpaca: %s", response.text)
                    raise BrokerConnectionError(f"Connection failed: {response.text}")

            except requests.exceptions.RequestException as e:
                logger.error("Failed to connect to Alpaca: %s", str(e), exc_info=True)
                raise BrokerConnectionError(f"Failed to connect to Alpaca: {e}")

    def disconnect(self) -> None:
        """
        Disconnect from Alpaca and close the session.

        Safely closes the HTTP session and marks the broker as disconnected.
        Thread-safe operation.

        Example:
            >>> broker.disconnect()
            >>> broker.connected  # False
        """
        with self._lock:
            if hasattr(self, '_session'):
                self._session.close()
            self._connected = False
            logger.info("Disconnected from Alpaca")

    def get_account(self) -> BrokerAccount:
        """
        Get account information from Alpaca.

        Retrieves current account details including cash, buying power,
        and portfolio value. This is the primary method for monitoring
        account status and available trading capital.

        Returns:
            BrokerAccount with current account details including:
            - Account number
            - Cash available
            - Buying power
            - Portfolio value
            - Equity

        Raises:
            BrokerError: If not connected or request fails
            requests.exceptions.RequestException: If API call fails

        Example:
            >>> account = broker.get_account()
            >>> print(f"Buying power: ${account.buying_power}")
            >>> print(f"Cash: ${account.cash}")

        Performance:
            Typical execution: 100-300ms
        """
        if not self.connected:
            logger.error("Cannot get account: not connected to broker")
            raise BrokerError("Not connected to broker")

        try:
            logger.debug("Fetching account information from Alpaca")
            response = self._api_request("GET", "account")
            response.raise_for_status()
            data = response.json()

            account = BrokerAccount(
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

            logger.debug("Account retrieved: cash=%.2f, buying_power=%.2f, portfolio_value=%.2f",
                        account.cash, account.buying_power, account.portfolio_value)
            return account

        except requests.exceptions.RequestException as e:
            logger.error("Failed to get account: %s", str(e), exc_info=True)
            raise BrokerError(f"Failed to get account: {e}")

    def get_positions(self) -> List[BrokerPosition]:
        """
        Get all current positions held in the account.

        Retrieves a list of all active positions, including quantity,
        entry price, current price, and unrealized P&L for each position.

        Returns:
            List of BrokerPosition objects containing:
            - Symbol
            - Quantity held
            - Average entry price
            - Current market price
            - Market value
            - Unrealized P&L and percentage

        Raises:
            BrokerError: If not connected or request fails

        Example:
            >>> positions = broker.get_positions()
            >>> for pos in positions:
            ...     print(f"{pos.symbol}: {pos.quantity} shares, P&L: ${pos.unrealized_pnl}")

        Performance:
            Typical execution: 100-300ms
        """
        if not self.connected:
            logger.error("Cannot get positions: not connected to broker")
            raise BrokerError("Not connected to broker")

        try:
            logger.debug("Fetching positions from Alpaca")
            response = self._api_request("GET", "positions")
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

            logger.debug("Retrieved %d positions", len(positions))
            return positions

        except requests.exceptions.RequestException as e:
            logger.error("Failed to get positions: %s", str(e), exc_info=True)
            raise BrokerError(f"Failed to get positions: {e}")

    def get_position(self, symbol: str) -> Optional[BrokerPosition]:
        """
        Get position for a specific symbol.

        Retrieves detailed information for a single symbol including
        quantity, entry price, and P&L metrics.

        Args:
            symbol: Stock ticker symbol (e.g., "AAPL", "NVDA")

        Returns:
            BrokerPosition if position exists, None if no position held

        Raises:
            BrokerError: If not connected or API request fails

        Example:
            >>> pos = broker.get_position("AAPL")
            >>> if pos:
            ...     print(f"AAPL: {pos.quantity} shares, P&L: ${pos.unrealized_pnl}")
            ... else:
            ...     print("No AAPL position")

        Performance:
            Typical execution: 100-300ms
        """
        if not self.connected:
            logger.error("Cannot get position: not connected to broker")
            raise BrokerError("Not connected to broker")

        try:
            logger.debug("Fetching position for %s from Alpaca", symbol)
            response = self._api_request("GET", f"positions/{symbol}")

            if response.status_code == 404:
                logger.debug("No position found for symbol: %s", symbol)
                return None

            response.raise_for_status()
            pos = response.json()

            position = BrokerPosition(
                symbol=pos["symbol"],
                quantity=Decimal(pos["qty"]),
                avg_entry_price=Decimal(pos["avg_entry_price"]),
                current_price=Decimal(pos["current_price"]),
                market_value=Decimal(pos["market_value"]),
                unrealized_pnl=Decimal(pos["unrealized_pl"]),
                unrealized_pnl_percent=Decimal(pos["unrealized_plpc"]),
                cost_basis=Decimal(pos["cost_basis"]),
            )

            logger.debug("Position retrieved: %s qty=%s, price=%.2f, pnl=%.2f",
                        symbol, position.quantity, position.current_price, position.unrealized_pnl)
            return position

        except requests.exceptions.RequestException as e:
            logger.error("Failed to get position for %s: %s", symbol, str(e), exc_info=True)
            raise BrokerError(f"Failed to get position for {symbol}: {e}")

    def submit_order(self, order: BrokerOrder) -> BrokerOrder:
        """
        Submit an order to Alpaca for execution.

        This method validates the order, applies rate limiting, sends it to
        the Alpaca API, and returns the updated order with ID and status.

        Args:
            order: BrokerOrder instance with symbol, side, quantity, and type

        Returns:
            BrokerOrder: Updated order with order_id, status, and timestamps

        Raises:
            BrokerError: If not connected to broker
            OrderError: If order validation or submission fails
            InsufficientFundsError: If account lacks sufficient buying power

        Example:
            >>> broker = AlpacaBroker(paper_trading=True)
            >>> broker.connect()
            >>> order = BrokerOrder(
            ...     symbol="AAPL",
            ...     side=OrderSide.BUY,
            ...     quantity=Decimal("10"),
            ...     order_type=OrderType.MARKET
            ... )
            >>> result = broker.submit_order(order)
            >>> print(f"Order ID: {result.order_id}, Status: {result.status.value}")

        Performance:
            Typical execution: 200-500ms (includes rate limiting and network)

        Note:
            All orders are rate-limited to comply with Alpaca's 200 req/min limit.
        """
        if not self.connected:
            logger.error("Cannot submit order: not connected to broker")
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
                logger.error("Limit price required for %s order on %s", order.order_type.value, order.symbol)
                raise OrderError("Limit price required for limit orders")
            payload["limit_price"] = str(order.limit_price)

        # Add stop price if needed
        if order.order_type in [OrderType.STOP, OrderType.STOP_LIMIT]:
            if order.stop_price is None:
                logger.error("Stop price required for %s order on %s", order.order_type.value, order.symbol)
                raise OrderError("Stop price required for stop orders")
            payload["stop_price"] = str(order.stop_price)

        logger.info("Submitting order: %s %s %s shares", order.side.value, order.symbol, order.quantity)

        try:
            response = self._api_request("POST", "orders", json=payload)

            # Check for insufficient funds
            if response.status_code == 403:
                error_msg = response.json().get("message", "")
                if "insufficient" in error_msg.lower():
                    logger.warning("Order rejected - insufficient funds: %s", error_msg)
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

            logger.info("Order submitted successfully: %s (ID: %s, Status: %s)",
                       order.symbol, order.order_id, order.status.value)
            return order

        except InsufficientFundsError:
            raise
        except requests.exceptions.RequestException as e:
            logger.error("Order submission failed: %s", str(e), exc_info=True)
            raise OrderError(f"Failed to submit order: {e}")

    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an existing order.

        Attempts to cancel an order that is still pending or open.
        Once filled, an order cannot be cancelled.

        Args:
            order_id: Alpaca order ID to cancel

        Returns:
            True if cancellation successful

        Raises:
            BrokerError: If not connected to broker
            OrderError: If order not found or cancellation fails

        Example:
            >>> success = broker.cancel_order("67e7e8c0-b3f0-4e3e-b5e5-5d5f5e5f5e5f")
            >>> if success:
            ...     print("Order cancelled")

        Performance:
            Typical execution: 100-300ms
        """
        if not self.connected:
            logger.error("Cannot cancel order: not connected to broker")
            raise BrokerError("Not connected to broker")

        logger.info("Cancelling order: %s", order_id)

        try:
            response = self._api_request("DELETE", f"orders/{order_id}")

            if response.status_code == 404:
                logger.warning("Order not found: %s", order_id)
                raise OrderError(f"Order {order_id} not found")

            response.raise_for_status()
            logger.info("Order cancelled successfully: %s", order_id)
            return True

        except requests.exceptions.RequestException as e:
            logger.error("Failed to cancel order %s: %s", order_id, str(e), exc_info=True)
            raise OrderError(f"Failed to cancel order: {e}")

    def get_order(self, order_id: str) -> Optional[BrokerOrder]:
        """
        Get order status by order ID.

        Retrieves detailed information about a specific order including
        its current status, fill quantity, and fill price.

        Args:
            order_id: Alpaca order ID

        Returns:
            BrokerOrder if found, None if order does not exist

        Raises:
            BrokerError: If not connected or API request fails

        Example:
            >>> order = broker.get_order("67e7e8c0-b3f0-4e3e-b5e5-5d5f5e5f5e5f")
            >>> if order:
            ...     print(f"Order status: {order.status.value}, Filled: {order.filled_qty}")

        Performance:
            Typical execution: 100-300ms
        """
        if not self.connected:
            logger.error("Cannot get order: not connected to broker")
            raise BrokerError("Not connected to broker")

        try:
            logger.debug("Fetching order status: %s", order_id)
            response = self._api_request("GET", f"orders/{order_id}")

            if response.status_code == 404:
                logger.debug("Order not found: %s", order_id)
                return None

            response.raise_for_status()
            data = response.json()

            order = self._convert_alpaca_order(data)
            logger.debug("Order retrieved: %s status=%s, filled=%s",
                        order_id, order.status.value, order.filled_qty)
            return order

        except requests.exceptions.RequestException as e:
            logger.error("Failed to get order %s: %s", order_id, str(e), exc_info=True)
            raise BrokerError(f"Failed to get order: {e}")

    def get_orders(
        self,
        status: Optional[OrderStatus] = None,
        limit: int = 50
    ) -> List[BrokerOrder]:
        """
        Get orders with optional filtering by status.

        Retrieves a list of orders, optionally filtered by order status.
        Useful for monitoring order activity and history.

        Args:
            status: Filter by order status (None for all statuses)
            limit: Maximum number of orders to return (default 50)

        Returns:
            List of BrokerOrder objects

        Raises:
            BrokerError: If not connected or API request fails

        Example:
            >>> open_orders = broker.get_orders(status=OrderStatus.SUBMITTED)
            >>> print(f"Open orders: {len(open_orders)}")

        Performance:
            Typical execution: 100-300ms
        """
        if not self.connected:
            logger.error("Cannot get orders: not connected to broker")
            raise BrokerError("Not connected to broker")

        params = {"limit": limit}
        if status:
            params["status"] = self._convert_status_to_alpaca(status)

        logger.debug("Fetching orders from Alpaca (status=%s, limit=%d)", status, limit)

        try:
            response = self._api_request("GET", "orders", params=params)
            response.raise_for_status()
            data = response.json()

            orders = [self._convert_alpaca_order(order) for order in data]
            logger.debug("Retrieved %d orders", len(orders))
            return orders

        except requests.exceptions.RequestException as e:
            logger.error("Failed to get orders: %s", str(e), exc_info=True)
            raise BrokerError(f"Failed to get orders: {e}")

    def get_current_price(self, symbol: str) -> Decimal:
        """
        Get current market price for a symbol.

        Retrieves the latest trade price for a security. Uses the Alpaca
        trades/latest endpoint for real-time pricing data.

        Args:
            symbol: Stock ticker symbol (e.g., "AAPL", "NVDA")

        Returns:
            Current market price as Decimal

        Raises:
            BrokerError: If not connected or price cannot be retrieved

        Example:
            >>> price = broker.get_current_price("AAPL")
            >>> print(f"AAPL: ${price}")

        Performance:
            Typical execution: 100-300ms
        """
        if not self.connected:
            logger.error("Cannot get price: not connected to broker")
            raise BrokerError("Not connected to broker")

        try:
            logger.debug("Fetching current price for %s", symbol)
            # Use latest trade endpoint
            response = self._api_request("GET", f"stocks/{symbol}/trades/latest")
            response.raise_for_status()
            data = response.json()

            price = Decimal(str(data["trade"]["p"]))
            logger.debug("Current price for %s: %.2f", symbol, price)
            return price

        except requests.exceptions.RequestException as e:
            logger.error("Failed to get price for %s: %s", symbol, str(e), exc_info=True)
            raise BrokerError(f"Failed to get price for {symbol}: {e}")

    # Helper methods

    def _convert_order_type(self, order_type: OrderType) -> str:
        """
        Convert OrderType enum to Alpaca API order type string.

        Args:
            order_type: OrderType enum value

        Returns:
            Alpaca order type string ("market", "limit", "stop", "stop_limit")
        """
        mapping = {
            OrderType.MARKET: "market",
            OrderType.LIMIT: "limit",
            OrderType.STOP: "stop",
            OrderType.STOP_LIMIT: "stop_limit",
        }
        return mapping[order_type]

    def _convert_order_status(self, alpaca_status: str) -> OrderStatus:
        """
        Convert Alpaca API order status to OrderStatus enum.

        Maps Alpaca's internal status values to our standardized
        OrderStatus enumeration.

        Args:
            alpaca_status: Alpaca order status string

        Returns:
            OrderStatus enum value
        """
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
        """
        Convert OrderStatus enum to Alpaca API status filter.

        Maps our standardized OrderStatus to Alpaca's query parameters.

        Args:
            status: OrderStatus enum value

        Returns:
            Alpaca status filter string
        """
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
        """
        Convert Alpaca order API response to BrokerOrder object.

        Transforms the API response JSON into our standardized BrokerOrder
        format for consistent internal representation.

        Args:
            data: Alpaca order API response dictionary

        Returns:
            BrokerOrder instance with all fields populated
        """
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
        """
        Parse Alpaca order type string to OrderType enum.

        Converts Alpaca's order type representation to our standardized
        OrderType enumeration.

        Args:
            alpaca_type: Alpaca order type string

        Returns:
            OrderType enum value (defaults to MARKET if unknown)
        """
        mapping = {
            "market": OrderType.MARKET,
            "limit": OrderType.LIMIT,
            "stop": OrderType.STOP,
            "stop_limit": OrderType.STOP_LIMIT,
        }
        return mapping.get(alpaca_type, OrderType.MARKET)
