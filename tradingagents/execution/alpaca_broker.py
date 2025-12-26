"""Alpaca Broker implementation.

Issue #24: [EXEC-23] Alpaca broker - US stocks, ETFs, crypto

This module provides a concrete implementation of BrokerBase for the Alpaca
trading platform. Alpaca supports:
- US Stocks and ETFs (commission-free)
- Cryptocurrency trading
- Paper trading mode for testing
- Extended hours trading

Requirements:
    pip install alpaca-py

Environment Variables:
    ALPACA_API_KEY: Your Alpaca API key
    ALPACA_API_SECRET: Your Alpaca API secret
    ALPACA_PAPER: Set to 'true' for paper trading (default: true)

Example:
    >>> from tradingagents.execution import AlpacaBroker, OrderRequest, OrderSide
    >>>
    >>> broker = AlpacaBroker(
    ...     api_key="your-api-key",
    ...     api_secret="your-api-secret",
    ...     paper_trading=True,
    ... )
    >>>
    >>> await broker.connect()
    >>> order = await broker.submit_order(
    ...     OrderRequest.market("AAPL", OrderSide.BUY, 10)
    ... )
    >>> print(f"Order placed: {order.broker_order_id}")
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from .broker_base import (
    AccountInfo,
    AssetClass,
    AssetInfo,
    AuthenticationError,
    BrokerBase,
    BrokerError,
    ConnectionError,
    InsufficientFundsError,
    InvalidOrderError,
    Order,
    OrderError,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    PositionError,
    PositionSide,
    Quote,
    RateLimitError,
    TimeInForce,
)


# Try to import alpaca-py, provide stubs for testing without it
try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import (
        GetOrdersRequest,
        LimitOrderRequest,
        MarketOrderRequest,
        ReplaceOrderRequest,
        StopLimitOrderRequest,
        StopOrderRequest,
        TrailingStopOrderRequest,
    )
    from alpaca.trading.enums import (
        OrderSide as AlpacaOrderSide,
        OrderType as AlpacaOrderType,
        OrderStatus as AlpacaOrderStatus,
        TimeInForce as AlpacaTimeInForce,
        QueryOrderStatus,
        PositionSide as AlpacaPositionSide,
    )
    from alpaca.data.live import StockDataStream, CryptoDataStream
    from alpaca.data.historical import StockHistoricalDataClient, CryptoHistoricalDataClient
    from alpaca.data.requests import StockLatestQuoteRequest, CryptoLatestQuoteRequest

    ALPACA_AVAILABLE = True
except ImportError:
    ALPACA_AVAILABLE = False
    TradingClient = None
    StockDataStream = None
    CryptoDataStream = None
    StockHistoricalDataClient = None
    CryptoHistoricalDataClient = None
    StockLatestQuoteRequest = None
    CryptoLatestQuoteRequest = None
    # Enums stubs
    AlpacaOrderSide = None
    AlpacaOrderType = None
    AlpacaOrderStatus = None
    AlpacaTimeInForce = None
    QueryOrderStatus = None


class AlpacaBroker(BrokerBase):
    """Alpaca broker implementation.

    Supports US stocks, ETFs, and cryptocurrency trading through the
    Alpaca API. Provides both paper and live trading modes.

    Attributes:
        api_key: Alpaca API key
        api_secret: Alpaca API secret
        base_url: Alpaca API base URL
        data_url: Alpaca data API URL

    Example:
        >>> broker = AlpacaBroker(
        ...     api_key="PKXXXXXXXXXX",
        ...     api_secret="xxxxxxxxxxxxxxxxxx",
        ...     paper_trading=True,
        ... )
        >>> await broker.connect()
        >>> account = await broker.get_account()
        >>> print(f"Cash: ${account.cash}")
    """

    # Alpaca API endpoints
    LIVE_URL = "https://api.alpaca.markets"
    PAPER_URL = "https://paper-api.alpaca.markets"
    DATA_URL = "https://data.alpaca.markets"

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        paper_trading: bool = True,
        **kwargs: Any,
    ) -> None:
        """Initialize Alpaca broker.

        Args:
            api_key: Alpaca API key. If not provided, reads from
                ALPACA_API_KEY environment variable.
            api_secret: Alpaca API secret. If not provided, reads from
                ALPACA_API_SECRET environment variable.
            paper_trading: If True, use paper trading account.
                Defaults to True for safety.
            **kwargs: Additional arguments passed to BrokerBase.
        """
        super().__init__(
            name="Alpaca",
            supported_asset_classes=[
                AssetClass.EQUITY,
                AssetClass.ETF,
                AssetClass.CRYPTO,
            ],
            paper_trading=paper_trading,
            **kwargs,
        )

        self._api_key = api_key or os.environ.get("ALPACA_API_KEY", "")
        self._api_secret = api_secret or os.environ.get("ALPACA_API_SECRET", "")
        self._base_url = self.PAPER_URL if paper_trading else self.LIVE_URL
        self._data_url = self.DATA_URL

        self._trading_client: Optional[TradingClient] = None
        self._stock_data_client: Optional[Any] = None
        self._crypto_data_client: Optional[Any] = None
        self._stock_stream: Optional[Any] = None
        self._crypto_stream: Optional[Any] = None

    @property
    def api_key(self) -> str:
        """Get API key (masked)."""
        if len(self._api_key) > 8:
            return self._api_key[:4] + "****" + self._api_key[-4:]
        return "****"

    @property
    def base_url(self) -> str:
        """Get API base URL."""
        return self._base_url

    def _require_connection(self) -> None:
        """Require broker to be connected.

        Raises:
            ConnectionError: If not connected.
        """
        if not self.is_connected:
            raise ConnectionError("Not connected to Alpaca. Call connect() first.")

    def _check_alpaca_available(self) -> None:
        """Check if alpaca-py is installed."""
        if not ALPACA_AVAILABLE:
            raise BrokerError(
                "alpaca-py is not installed. "
                "Install it with: pip install alpaca-py"
            )

    async def connect(self) -> bool:
        """Connect to Alpaca API.

        Returns:
            True if connection successful.

        Raises:
            AuthenticationError: If API credentials are invalid.
            ConnectionError: If connection fails.
        """
        self._check_alpaca_available()

        if not self._api_key or not self._api_secret:
            raise AuthenticationError(
                "Alpaca API credentials not provided. "
                "Set ALPACA_API_KEY and ALPACA_API_SECRET environment variables "
                "or pass api_key and api_secret to constructor."
            )

        try:
            # Initialize trading client
            self._trading_client = TradingClient(
                api_key=self._api_key,
                secret_key=self._api_secret,
                paper=self._paper_trading,
            )

            # Verify connection by getting account
            account = self._trading_client.get_account()
            if account.status != "ACTIVE":
                raise AuthenticationError(
                    f"Alpaca account is not active: {account.status}"
                )

            # Initialize data clients
            self._stock_data_client = StockHistoricalDataClient(
                api_key=self._api_key,
                secret_key=self._api_secret,
            )
            self._crypto_data_client = CryptoHistoricalDataClient(
                api_key=self._api_key,
                secret_key=self._api_secret,
            )

            self._connected = True
            return True

        except Exception as e:
            error_msg = str(e).lower()
            if "unauthorized" in error_msg or "forbidden" in error_msg:
                raise AuthenticationError(f"Alpaca authentication failed: {e}")
            elif "connect" in error_msg or "timeout" in error_msg:
                raise ConnectionError(f"Failed to connect to Alpaca: {e}")
            else:
                raise BrokerError(f"Alpaca connection error: {e}")

    async def disconnect(self) -> None:
        """Disconnect from Alpaca API."""
        # Close streaming connections if active
        if self._stock_stream:
            await self._stock_stream.close()
            self._stock_stream = None

        if self._crypto_stream:
            await self._crypto_stream.close()
            self._crypto_stream = None

        self._trading_client = None
        self._stock_data_client = None
        self._crypto_data_client = None
        self._connected = False

    async def is_market_open(self) -> bool:
        """Check if the market is currently open.

        Returns:
            True if market is open for trading.
        """
        self._require_connection()

        try:
            clock = self._trading_client.get_clock()
            return clock.is_open
        except Exception as e:
            raise BrokerError(f"Failed to get market status: {e}")

    async def get_account(self) -> AccountInfo:
        """Get account information.

        Returns:
            AccountInfo with current account state.

        Raises:
            BrokerError: If account retrieval fails.
        """
        self._require_connection()

        try:
            account = self._trading_client.get_account()

            return AccountInfo(
                account_id=account.account_number,
                account_type=account.account_type or "margin",
                status=account.status,
                cash=Decimal(str(account.cash)),
                portfolio_value=Decimal(str(account.portfolio_value or 0)),
                buying_power=Decimal(str(account.buying_power)),
                equity=Decimal(str(account.equity)),
                margin_used=Decimal(str(account.initial_margin or 0)),
                margin_available=Decimal(str(account.regt_buying_power or 0)),
                day_trades_remaining=account.daytrade_count or 0,
                is_pattern_day_trader=account.pattern_day_trader or False,
            )
        except Exception as e:
            raise BrokerError(f"Failed to get account: {e}")

    def _map_order_side(self, side: OrderSide) -> "AlpacaOrderSide":
        """Map internal order side to Alpaca order side."""
        return AlpacaOrderSide.BUY if side == OrderSide.BUY else AlpacaOrderSide.SELL

    def _map_time_in_force(self, tif: TimeInForce) -> "AlpacaTimeInForce":
        """Map internal time in force to Alpaca time in force."""
        mapping = {
            TimeInForce.DAY: AlpacaTimeInForce.DAY,
            TimeInForce.GTC: AlpacaTimeInForce.GTC,
            TimeInForce.IOC: AlpacaTimeInForce.IOC,
            TimeInForce.FOK: AlpacaTimeInForce.FOK,
            TimeInForce.OPG: AlpacaTimeInForce.OPG,
            TimeInForce.CLS: AlpacaTimeInForce.CLS,
        }
        return mapping.get(tif, AlpacaTimeInForce.DAY)

    def _map_alpaca_order_status(self, status: "AlpacaOrderStatus") -> OrderStatus:
        """Map Alpaca order status to internal order status."""
        mapping = {
            AlpacaOrderStatus.NEW: OrderStatus.NEW,
            AlpacaOrderStatus.ACCEPTED: OrderStatus.NEW,
            AlpacaOrderStatus.PENDING_NEW: OrderStatus.PENDING,
            AlpacaOrderStatus.ACCEPTED_FOR_BIDDING: OrderStatus.PENDING,
            AlpacaOrderStatus.PARTIALLY_FILLED: OrderStatus.PARTIALLY_FILLED,
            AlpacaOrderStatus.FILLED: OrderStatus.FILLED,
            AlpacaOrderStatus.DONE_FOR_DAY: OrderStatus.FILLED,
            AlpacaOrderStatus.CANCELED: OrderStatus.CANCELLED,
            AlpacaOrderStatus.EXPIRED: OrderStatus.EXPIRED,
            AlpacaOrderStatus.REPLACED: OrderStatus.REPLACED,
            AlpacaOrderStatus.PENDING_CANCEL: OrderStatus.PENDING,
            AlpacaOrderStatus.PENDING_REPLACE: OrderStatus.PENDING,
            AlpacaOrderStatus.STOPPED: OrderStatus.CANCELLED,
            AlpacaOrderStatus.REJECTED: OrderStatus.REJECTED,
            AlpacaOrderStatus.SUSPENDED: OrderStatus.CANCELLED,
            AlpacaOrderStatus.CALCULATED: OrderStatus.NEW,
        }
        return mapping.get(status, OrderStatus.NEW)

    def _map_alpaca_order_type(self, order_type: "AlpacaOrderType") -> OrderType:
        """Map Alpaca order type to internal order type."""
        mapping = {
            AlpacaOrderType.MARKET: OrderType.MARKET,
            AlpacaOrderType.LIMIT: OrderType.LIMIT,
            AlpacaOrderType.STOP: OrderType.STOP,
            AlpacaOrderType.STOP_LIMIT: OrderType.STOP_LIMIT,
            AlpacaOrderType.TRAILING_STOP: OrderType.TRAILING_STOP,
        }
        return mapping.get(order_type, OrderType.MARKET)

    def _convert_alpaca_order(self, alpaca_order: Any) -> Order:
        """Convert Alpaca order to internal Order type."""
        return Order(
            broker_order_id=str(alpaca_order.id),
            client_order_id=alpaca_order.client_order_id,
            symbol=alpaca_order.symbol,
            side=OrderSide.BUY if alpaca_order.side == AlpacaOrderSide.BUY else OrderSide.SELL,
            quantity=Decimal(str(alpaca_order.qty)),
            order_type=self._map_alpaca_order_type(alpaca_order.order_type),
            status=self._map_alpaca_order_status(alpaca_order.status),
            limit_price=Decimal(str(alpaca_order.limit_price)) if alpaca_order.limit_price else None,
            stop_price=Decimal(str(alpaca_order.stop_price)) if alpaca_order.stop_price else None,
            time_in_force=TimeInForce(alpaca_order.time_in_force.value.lower()),
            filled_quantity=Decimal(str(alpaca_order.filled_qty or 0)),
            avg_fill_price=Decimal(str(alpaca_order.filled_avg_price)) if alpaca_order.filled_avg_price else None,
            created_at=alpaca_order.created_at,
            updated_at=alpaca_order.updated_at,
            submitted_at=alpaca_order.submitted_at,
            filled_at=alpaca_order.filled_at,
            expired_at=alpaca_order.expired_at,
            cancelled_at=alpaca_order.canceled_at,
        )

    async def submit_order(self, request: OrderRequest) -> Order:
        """Submit an order to Alpaca.

        Args:
            request: Order request details.

        Returns:
            Order with broker order ID.

        Raises:
            InvalidOrderError: If order parameters are invalid.
            InsufficientFundsError: If insufficient buying power.
            OrderError: If order submission fails.
        """
        self._require_connection()

        try:
            # Build order request based on order type
            if request.order_type == OrderType.MARKET:
                alpaca_request = MarketOrderRequest(
                    symbol=request.symbol,
                    qty=float(request.quantity),
                    side=self._map_order_side(request.side),
                    time_in_force=self._map_time_in_force(request.time_in_force),
                    client_order_id=request.client_order_id,
                    extended_hours=request.extended_hours,
                )

            elif request.order_type == OrderType.LIMIT:
                if request.limit_price is None:
                    raise InvalidOrderError("Limit price required for limit orders")

                alpaca_request = LimitOrderRequest(
                    symbol=request.symbol,
                    qty=float(request.quantity),
                    side=self._map_order_side(request.side),
                    time_in_force=self._map_time_in_force(request.time_in_force),
                    limit_price=float(request.limit_price),
                    client_order_id=request.client_order_id,
                    extended_hours=request.extended_hours,
                )

            elif request.order_type == OrderType.STOP:
                if request.stop_price is None:
                    raise InvalidOrderError("Stop price required for stop orders")

                alpaca_request = StopOrderRequest(
                    symbol=request.symbol,
                    qty=float(request.quantity),
                    side=self._map_order_side(request.side),
                    time_in_force=self._map_time_in_force(request.time_in_force),
                    stop_price=float(request.stop_price),
                    client_order_id=request.client_order_id,
                )

            elif request.order_type == OrderType.STOP_LIMIT:
                if request.stop_price is None:
                    raise InvalidOrderError("Stop price required for stop-limit orders")
                if request.limit_price is None:
                    raise InvalidOrderError("Limit price required for stop-limit orders")

                alpaca_request = StopLimitOrderRequest(
                    symbol=request.symbol,
                    qty=float(request.quantity),
                    side=self._map_order_side(request.side),
                    time_in_force=self._map_time_in_force(request.time_in_force),
                    stop_price=float(request.stop_price),
                    limit_price=float(request.limit_price),
                    client_order_id=request.client_order_id,
                )

            elif request.order_type == OrderType.TRAILING_STOP:
                if request.trail_percent is None and request.trail_price is None:
                    raise InvalidOrderError(
                        "Trail percent or trail price required for trailing stop orders"
                    )

                alpaca_request = TrailingStopOrderRequest(
                    symbol=request.symbol,
                    qty=float(request.quantity),
                    side=self._map_order_side(request.side),
                    time_in_force=self._map_time_in_force(request.time_in_force),
                    trail_percent=float(request.trail_percent) if request.trail_percent else None,
                    trail_price=float(request.trail_price) if request.trail_price else None,
                    client_order_id=request.client_order_id,
                )

            else:
                raise InvalidOrderError(f"Unsupported order type: {request.order_type}")

            # Submit order
            alpaca_order = self._trading_client.submit_order(alpaca_request)

            return self._convert_alpaca_order(alpaca_order)

        except InvalidOrderError:
            raise
        except Exception as e:
            error_msg = str(e).lower()
            if "insufficient" in error_msg or "buying power" in error_msg:
                raise InsufficientFundsError(f"Insufficient funds for order: {e}")
            elif "invalid" in error_msg or "validation" in error_msg:
                raise InvalidOrderError(f"Invalid order: {e}")
            elif "rate" in error_msg and "limit" in error_msg:
                raise RateLimitError(f"Alpaca rate limit exceeded: {e}")
            else:
                raise OrderError(f"Failed to submit order: {e}")

    async def cancel_order(self, order_id: str) -> Order:
        """Cancel an order.

        Args:
            order_id: Broker order ID to cancel.

        Returns:
            Updated order with cancelled status.

        Raises:
            OrderError: If cancellation fails.
        """
        self._require_connection()

        try:
            self._trading_client.cancel_order_by_id(order_id)

            # Get updated order
            alpaca_order = self._trading_client.get_order_by_id(order_id)
            return self._convert_alpaca_order(alpaca_order)

        except Exception as e:
            raise OrderError(f"Failed to cancel order {order_id}: {e}")

    async def replace_order(
        self,
        order_id: str,
        quantity: Optional[Decimal] = None,
        limit_price: Optional[Decimal] = None,
        stop_price: Optional[Decimal] = None,
        time_in_force: Optional[TimeInForce] = None,
    ) -> Order:
        """Replace/modify an existing order.

        Args:
            order_id: Broker order ID to replace.
            quantity: New quantity (optional).
            limit_price: New limit price (optional).
            stop_price: New stop price (optional).
            time_in_force: New time in force (optional).

        Returns:
            New order that replaced the original.

        Raises:
            OrderError: If replacement fails.
        """
        self._require_connection()

        try:
            replace_request = ReplaceOrderRequest(
                qty=float(quantity) if quantity else None,
                limit_price=float(limit_price) if limit_price else None,
                stop_price=float(stop_price) if stop_price else None,
                time_in_force=self._map_time_in_force(time_in_force) if time_in_force else None,
            )

            alpaca_order = self._trading_client.replace_order_by_id(
                order_id=order_id,
                order_data=replace_request,
            )

            return self._convert_alpaca_order(alpaca_order)

        except Exception as e:
            raise OrderError(f"Failed to replace order {order_id}: {e}")

    async def get_order(self, order_id: str) -> Order:
        """Get order by ID.

        Args:
            order_id: Broker order ID.

        Returns:
            Order details.

        Raises:
            OrderError: If order not found or retrieval fails.
        """
        self._require_connection()

        try:
            alpaca_order = self._trading_client.get_order_by_id(order_id)
            return self._convert_alpaca_order(alpaca_order)

        except Exception as e:
            raise OrderError(f"Failed to get order {order_id}: {e}")

    async def get_orders(
        self,
        status: Optional[OrderStatus] = None,
        limit: int = 100,
        symbols: Optional[List[str]] = None,
    ) -> List[Order]:
        """Get orders with optional filters.

        Args:
            status: Filter by order status.
            limit: Maximum number of orders to return.
            symbols: Filter by symbols.

        Returns:
            List of orders.
        """
        self._require_connection()

        try:
            # Map status to query status
            if status == OrderStatus.NEW:
                query_status = QueryOrderStatus.OPEN
            elif status in (OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED):
                query_status = QueryOrderStatus.CLOSED
            else:
                query_status = QueryOrderStatus.ALL

            request = GetOrdersRequest(
                status=query_status,
                limit=limit,
                symbols=symbols,
            )

            alpaca_orders = self._trading_client.get_orders(request)

            orders = [self._convert_alpaca_order(o) for o in alpaca_orders]

            # Filter by exact status if needed
            if status:
                orders = [o for o in orders if o.status == status]

            return orders

        except Exception as e:
            raise BrokerError(f"Failed to get orders: {e}")

    async def get_positions(self) -> List[Position]:
        """Get all positions.

        Returns:
            List of current positions.
        """
        self._require_connection()

        try:
            alpaca_positions = self._trading_client.get_all_positions()

            positions = []
            for pos in alpaca_positions:
                position = Position(
                    symbol=pos.symbol,
                    quantity=Decimal(str(pos.qty)),
                    side=PositionSide.LONG if Decimal(str(pos.qty)) > 0 else PositionSide.SHORT,
                    avg_entry_price=Decimal(str(pos.avg_entry_price)),
                    current_price=Decimal(str(pos.current_price)),
                    market_value=Decimal(str(pos.market_value)),
                    cost_basis=Decimal(str(pos.cost_basis)),
                    unrealized_pnl=Decimal(str(pos.unrealized_pl)),
                    unrealized_pnl_percent=Decimal(str(pos.unrealized_plpc)) * 100,
                    asset_class=AssetClass.CRYPTO if pos.asset_class == "crypto" else AssetClass.EQUITY,
                )
                positions.append(position)

            return positions

        except Exception as e:
            raise PositionError(f"Failed to get positions: {e}")

    async def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for a specific symbol.

        Args:
            symbol: Symbol to get position for.

        Returns:
            Position if exists, None otherwise.
        """
        self._require_connection()

        try:
            pos = self._trading_client.get_open_position(symbol)

            return Position(
                symbol=pos.symbol,
                quantity=Decimal(str(pos.qty)),
                side=PositionSide.LONG if Decimal(str(pos.qty)) > 0 else PositionSide.SHORT,
                avg_entry_price=Decimal(str(pos.avg_entry_price)),
                current_price=Decimal(str(pos.current_price)),
                market_value=Decimal(str(pos.market_value)),
                cost_basis=Decimal(str(pos.cost_basis)),
                unrealized_pnl=Decimal(str(pos.unrealized_pl)),
                unrealized_pnl_percent=Decimal(str(pos.unrealized_plpc)) * 100,
                asset_class=AssetClass.CRYPTO if pos.asset_class == "crypto" else AssetClass.EQUITY,
            )

        except Exception as e:
            if "not found" in str(e).lower():
                return None
            raise PositionError(f"Failed to get position for {symbol}: {e}")

    async def get_quote(self, symbol: str) -> Quote:
        """Get current quote for a symbol.

        Args:
            symbol: Symbol to get quote for.

        Returns:
            Current quote data.
        """
        self._require_connection()

        try:
            # Determine if crypto or stock
            is_crypto = "/" in symbol or symbol.endswith("USD") or symbol.endswith("USDT")

            if is_crypto:
                # Use crypto data client
                request = CryptoLatestQuoteRequest(symbol_or_symbols=[symbol])
                quotes = self._crypto_data_client.get_crypto_latest_quote(request)
                quote_data = quotes[symbol]
            else:
                # Use stock data client
                request = StockLatestQuoteRequest(symbol_or_symbols=[symbol])
                quotes = self._stock_data_client.get_stock_latest_quote(request)
                quote_data = quotes[symbol]

            return Quote(
                symbol=symbol,
                bid_price=Decimal(str(quote_data.bid_price)) if quote_data.bid_price else None,
                ask_price=Decimal(str(quote_data.ask_price)) if quote_data.ask_price else None,
                bid_size=quote_data.bid_size,
                ask_size=quote_data.ask_size,
                timestamp=quote_data.timestamp,
            )

        except Exception as e:
            raise BrokerError(f"Failed to get quote for {symbol}: {e}")

    async def get_asset(self, symbol: str) -> AssetInfo:
        """Get asset information.

        Args:
            symbol: Symbol to get info for.

        Returns:
            Asset information.
        """
        self._require_connection()

        try:
            asset = self._trading_client.get_asset(symbol)

            # Determine asset class
            if asset.asset_class == "crypto":
                asset_class = AssetClass.CRYPTO
            elif asset.easy_to_borrow and asset.marginable:
                asset_class = AssetClass.ETF if asset.exchange == "ARCA" else AssetClass.EQUITY
            else:
                asset_class = AssetClass.EQUITY

            return AssetInfo(
                symbol=asset.symbol,
                name=asset.name or asset.symbol,
                asset_class=asset_class,
                exchange=asset.exchange,
                tradable=asset.tradable,
                shortable=asset.shortable,
                marginable=asset.marginable,
                fractionable=asset.fractionable,
            )

        except Exception as e:
            raise BrokerError(f"Failed to get asset info for {symbol}: {e}")


# Export
__all__ = ["AlpacaBroker", "ALPACA_AVAILABLE"]
