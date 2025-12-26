"""Interactive Brokers (IBKR) Broker implementation.

Issue #25: [EXEC-24] IBKR broker - futures, ASX equities

This module provides a concrete implementation of BrokerBase for Interactive
Brokers. IBKR supports:
- US and international equities (including ASX)
- Futures contracts
- Options contracts
- Forex
- Bonds

Requirements:
    pip install ib_insync

Configuration:
    IBKR_HOST: TWS/Gateway host (default: 127.0.0.1)
    IBKR_PORT: TWS/Gateway port (7497 paper, 7496 live)
    IBKR_CLIENT_ID: Client ID for connection

Example:
    >>> from tradingagents.execution import IBKRBroker, OrderRequest, OrderSide
    >>>
    >>> broker = IBKRBroker(
    ...     host="127.0.0.1",
    ...     port=7497,  # Paper trading port
    ...     client_id=1,
    ... )
    >>>
    >>> await broker.connect()
    >>> order = await broker.submit_order(
    ...     OrderRequest.market("ES", OrderSide.BUY, 1)  # E-mini S&P 500
    ... )
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

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


# Try to import ib_insync, provide stubs for testing without it
try:
    from ib_insync import (
        IB,
        Contract,
        Stock,
        Future,
        Option,
        Forex,
        Index,
        MarketOrder,
        LimitOrder,
        StopOrder,
        StopLimitOrder,
        Trade,
        Position as IBPosition,
        AccountValue,
        PortfolioItem,
        Ticker,
    )
    from ib_insync.order import Order as IBOrder

    IB_INSYNC_AVAILABLE = True
except ImportError:
    IB_INSYNC_AVAILABLE = False
    IB = None
    Contract = None
    Stock = None
    Future = None
    Option = None
    Forex = None
    Index = None
    MarketOrder = None
    LimitOrder = None
    StopOrder = None
    StopLimitOrder = None


# Common futures contract specifications
FUTURES_SPECS = {
    # US Index Futures
    "ES": {"exchange": "CME", "currency": "USD", "multiplier": 50},  # E-mini S&P 500
    "NQ": {"exchange": "CME", "currency": "USD", "multiplier": 20},  # E-mini NASDAQ-100
    "YM": {"exchange": "CBOT", "currency": "USD", "multiplier": 5},  # Mini Dow
    "RTY": {"exchange": "CME", "currency": "USD", "multiplier": 50},  # E-mini Russell 2000
    # Commodities
    "CL": {"exchange": "NYMEX", "currency": "USD", "multiplier": 1000},  # Crude Oil
    "GC": {"exchange": "COMEX", "currency": "USD", "multiplier": 100},  # Gold
    "SI": {"exchange": "COMEX", "currency": "USD", "multiplier": 5000},  # Silver
    "HG": {"exchange": "COMEX", "currency": "USD", "multiplier": 25000},  # Copper
    # Agricultural
    "ZC": {"exchange": "CBOT", "currency": "USD", "multiplier": 50},  # Corn
    "ZS": {"exchange": "CBOT", "currency": "USD", "multiplier": 50},  # Soybeans
    "ZW": {"exchange": "CBOT", "currency": "USD", "multiplier": 50},  # Wheat
    # Interest Rates
    "ZN": {"exchange": "CBOT", "currency": "USD", "multiplier": 1000},  # 10-Year T-Note
    "ZB": {"exchange": "CBOT", "currency": "USD", "multiplier": 1000},  # 30-Year T-Bond
    # Currency Futures
    "6E": {"exchange": "CME", "currency": "USD", "multiplier": 125000},  # Euro FX
    "6J": {"exchange": "CME", "currency": "USD", "multiplier": 12500000},  # Japanese Yen
    "6A": {"exchange": "CME", "currency": "USD", "multiplier": 100000},  # Australian Dollar
}

# ASX (Australian) stock exchange
ASX_EXCHANGE = "ASX"


class IBKRBroker(BrokerBase):
    """Interactive Brokers broker implementation.

    Supports US/international equities, futures, options, forex, and bonds
    through the Interactive Brokers TWS or Gateway API.

    Attributes:
        host: TWS/Gateway host address
        port: TWS/Gateway port (7497 paper, 7496 live)
        client_id: Client ID for connection

    Example:
        >>> broker = IBKRBroker(
        ...     host="127.0.0.1",
        ...     port=7497,  # Paper trading
        ...     client_id=1,
        ... )
        >>> await broker.connect()
        >>> positions = await broker.get_positions()
    """

    # Default ports
    PAPER_PORT = 7497
    LIVE_PORT = 7496
    GATEWAY_PAPER_PORT = 4002
    GATEWAY_LIVE_PORT = 4001

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        client_id: Optional[int] = None,
        paper_trading: bool = True,
        **kwargs: Any,
    ) -> None:
        """Initialize IBKR broker.

        Args:
            host: TWS/Gateway host. Default: 127.0.0.1 or IBKR_HOST env.
            port: TWS/Gateway port. Default: 7497 (paper) or 7496 (live).
            client_id: Client ID. Default: 1 or IBKR_CLIENT_ID env.
            paper_trading: If True, use paper trading account.
            **kwargs: Additional arguments passed to BrokerBase.
        """
        super().__init__(
            name="IBKR",
            supported_asset_classes=[
                AssetClass.EQUITY,
                AssetClass.ETF,
                AssetClass.FUTURE,
                AssetClass.OPTION,
                AssetClass.FOREX,
                AssetClass.BOND,
            ],
            paper_trading=paper_trading,
            **kwargs,
        )

        self._host = host or os.environ.get("IBKR_HOST", "127.0.0.1")
        self._port = port or int(
            os.environ.get(
                "IBKR_PORT",
                str(self.PAPER_PORT if paper_trading else self.LIVE_PORT)
            )
        )
        self._client_id = client_id or int(os.environ.get("IBKR_CLIENT_ID", "1"))

        self._ib: Optional["IB"] = None
        self._order_map: Dict[str, Tuple[Trade, Contract]] = {}
        self._next_order_id = 0

    @property
    def host(self) -> str:
        """Get host address."""
        return self._host

    @property
    def port(self) -> int:
        """Get port number."""
        return self._port

    @property
    def client_id(self) -> int:
        """Get client ID."""
        return self._client_id

    def _require_connection(self) -> None:
        """Require broker to be connected.

        Raises:
            ConnectionError: If not connected.
        """
        if not self.is_connected:
            raise ConnectionError("Not connected to IBKR. Call connect() first.")

    def _check_ib_insync_available(self) -> None:
        """Check if ib_insync is installed."""
        if not IB_INSYNC_AVAILABLE:
            raise BrokerError(
                "ib_insync is not installed. "
                "Install it with: pip install ib_insync"
            )

    async def connect(self) -> bool:
        """Connect to TWS/Gateway.

        Returns:
            True if connection successful.

        Raises:
            ConnectionError: If connection fails.
            AuthenticationError: If authentication fails.
        """
        self._check_ib_insync_available()

        try:
            self._ib = IB()

            # Connect to TWS/Gateway
            await self._ib.connectAsync(
                host=self._host,
                port=self._port,
                clientId=self._client_id,
            )

            if not self._ib.isConnected():
                raise ConnectionError(
                    f"Failed to connect to IBKR at {self._host}:{self._port}"
                )

            self._connected = True
            return True

        except Exception as e:
            error_msg = str(e).lower()
            if "connect" in error_msg or "timeout" in error_msg:
                raise ConnectionError(
                    f"Failed to connect to IBKR at {self._host}:{self._port}: {e}"
                )
            elif "auth" in error_msg or "permission" in error_msg:
                raise AuthenticationError(f"IBKR authentication failed: {e}")
            else:
                raise BrokerError(f"IBKR connection error: {e}")

    async def disconnect(self) -> None:
        """Disconnect from TWS/Gateway."""
        if self._ib:
            self._ib.disconnect()
            self._ib = None

        self._connected = False
        self._order_map.clear()

    async def is_market_open(self) -> bool:
        """Check if market is currently open.

        Note: IBKR doesn't have a simple market open check.
        This returns True if connected (simplified).
        """
        return self.is_connected

    async def get_account(self) -> AccountInfo:
        """Get account information.

        Returns:
            AccountInfo with current account state.
        """
        self._require_connection()

        try:
            # Get account values
            account_values = self._ib.accountValues()

            # Build dict from account values
            values = {}
            for av in account_values:
                if av.currency in ("USD", "BASE"):
                    values[av.tag] = av.value

            # Get portfolio summary
            portfolio = self._ib.portfolio()
            portfolio_value = sum(
                Decimal(str(item.marketValue or 0)) for item in portfolio
            )

            return AccountInfo(
                account_id=self._ib.managedAccounts()[0] if self._ib.managedAccounts() else "UNKNOWN",
                account_type=values.get("AccountType", "individual"),
                status="active",
                cash=Decimal(str(values.get("TotalCashValue", 0))),
                portfolio_value=portfolio_value,
                buying_power=Decimal(str(values.get("BuyingPower", 0))),
                equity=Decimal(str(values.get("NetLiquidation", 0))),
                margin_used=Decimal(str(values.get("MaintMarginReq", 0))),
                margin_available=Decimal(str(values.get("AvailableFunds", 0))),
            )

        except Exception as e:
            raise BrokerError(f"Failed to get account: {e}")

    def _create_contract(
        self,
        symbol: str,
        asset_class: Optional[AssetClass] = None,
        exchange: str = "SMART",
        currency: str = "USD",
        **kwargs: Any,
    ) -> "Contract":
        """Create IBKR contract from symbol.

        Args:
            symbol: Trading symbol
            asset_class: Asset class type
            exchange: Exchange (default: SMART routing)
            currency: Currency (default: USD)
            **kwargs: Additional contract parameters

        Returns:
            IBKR Contract object
        """
        # Check if it's a known futures symbol
        if symbol in FUTURES_SPECS:
            spec = FUTURES_SPECS[symbol]
            # Get expiry from kwargs or use front month
            expiry = kwargs.get("expiry", "")
            return Future(
                symbol=symbol,
                exchange=spec["exchange"],
                currency=spec["currency"],
                lastTradeDateOrContractMonth=expiry,
            )

        # Check if ASX symbol (Australian)
        if ".AX" in symbol.upper():
            symbol_clean = symbol.replace(".AX", "").replace(".ax", "")
            return Stock(
                symbol=symbol_clean,
                exchange=ASX_EXCHANGE,
                currency="AUD",
            )

        # Check asset class hints
        if asset_class == AssetClass.FUTURE:
            return Future(
                symbol=symbol,
                exchange=exchange,
                currency=currency,
                **kwargs,
            )
        elif asset_class == AssetClass.OPTION:
            return Option(
                symbol=symbol,
                exchange=exchange,
                currency=currency,
                **kwargs,
            )
        elif asset_class == AssetClass.FOREX:
            return Forex(pair=symbol)

        # Default to stock
        return Stock(
            symbol=symbol,
            exchange=exchange,
            currency=currency,
        )

    def _map_order_side(self, side: OrderSide) -> str:
        """Map internal order side to IBKR action."""
        return "BUY" if side == OrderSide.BUY else "SELL"

    def _map_time_in_force(self, tif: TimeInForce) -> str:
        """Map internal time in force to IBKR tif."""
        mapping = {
            TimeInForce.DAY: "DAY",
            TimeInForce.GTC: "GTC",
            TimeInForce.IOC: "IOC",
            TimeInForce.FOK: "FOK",
            TimeInForce.OPG: "OPG",
            TimeInForce.CLS: "CLS",
        }
        return mapping.get(tif, "DAY")

    def _map_ibkr_status(self, status: str) -> OrderStatus:
        """Map IBKR order status to internal status."""
        mapping = {
            "PendingSubmit": OrderStatus.PENDING_NEW,
            "PendingCancel": OrderStatus.PENDING_CANCEL,
            "PreSubmitted": OrderStatus.PENDING_NEW,
            "Submitted": OrderStatus.NEW,
            "Filled": OrderStatus.FILLED,
            "Cancelled": OrderStatus.CANCELLED,
            "Inactive": OrderStatus.CANCELLED,
            "ApiPending": OrderStatus.PENDING_NEW,
            "ApiCancelled": OrderStatus.CANCELLED,
        }
        return mapping.get(status, OrderStatus.NEW)

    def _convert_trade_to_order(self, trade: "Trade", contract: "Contract") -> Order:
        """Convert IBKR Trade to internal Order."""
        ib_order = trade.order
        order_status = trade.orderStatus

        return Order(
            broker_order_id=str(ib_order.orderId),
            client_order_id=str(ib_order.orderId),
            symbol=contract.symbol,
            side=OrderSide.BUY if ib_order.action == "BUY" else OrderSide.SELL,
            quantity=Decimal(str(abs(ib_order.totalQuantity))),
            order_type=OrderType.MARKET if isinstance(ib_order, MarketOrder) else OrderType.LIMIT,
            status=self._map_ibkr_status(order_status.status),
            limit_price=Decimal(str(ib_order.lmtPrice)) if hasattr(ib_order, 'lmtPrice') and ib_order.lmtPrice else None,
            stop_price=Decimal(str(ib_order.auxPrice)) if hasattr(ib_order, 'auxPrice') and ib_order.auxPrice else None,
            time_in_force=TimeInForce.DAY,
            filled_quantity=Decimal(str(order_status.filled or 0)),
            avg_fill_price=Decimal(str(order_status.avgFillPrice)) if order_status.avgFillPrice else None,
            created_at=datetime.now(timezone.utc),
        )

    async def submit_order(self, request: OrderRequest) -> Order:
        """Submit an order to IBKR.

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
            # Create contract
            contract = self._create_contract(
                symbol=request.symbol,
                asset_class=request.asset_class,
            )

            # Qualify contract
            qualified = await self._ib.qualifyContractsAsync(contract)
            if not qualified:
                raise InvalidOrderError(
                    f"Failed to qualify contract for {request.symbol}"
                )
            contract = qualified[0]

            # Create order based on type
            action = self._map_order_side(request.side)
            quantity = float(request.quantity)
            tif = self._map_time_in_force(request.time_in_force)

            if request.order_type == OrderType.MARKET:
                ib_order = MarketOrder(action=action, totalQuantity=quantity, tif=tif)

            elif request.order_type == OrderType.LIMIT:
                if request.limit_price is None:
                    raise InvalidOrderError("Limit price required for limit orders")
                ib_order = LimitOrder(
                    action=action,
                    totalQuantity=quantity,
                    lmtPrice=float(request.limit_price),
                    tif=tif,
                )

            elif request.order_type == OrderType.STOP:
                if request.stop_price is None:
                    raise InvalidOrderError("Stop price required for stop orders")
                ib_order = StopOrder(
                    action=action,
                    totalQuantity=quantity,
                    stopPrice=float(request.stop_price),
                    tif=tif,
                )

            elif request.order_type == OrderType.STOP_LIMIT:
                if request.stop_price is None or request.limit_price is None:
                    raise InvalidOrderError(
                        "Stop and limit prices required for stop-limit orders"
                    )
                ib_order = StopLimitOrder(
                    action=action,
                    totalQuantity=quantity,
                    stopPrice=float(request.stop_price),
                    lmtPrice=float(request.limit_price),
                    tif=tif,
                )

            else:
                raise InvalidOrderError(f"Unsupported order type: {request.order_type}")

            # Submit order
            trade = self._ib.placeOrder(contract, ib_order)

            # Wait for order to be acknowledged
            await asyncio.sleep(0.5)

            # Store mapping
            self._order_map[str(trade.order.orderId)] = (trade, contract)

            return self._convert_trade_to_order(trade, contract)

        except InvalidOrderError:
            raise
        except Exception as e:
            error_msg = str(e).lower()
            if "margin" in error_msg or "buying power" in error_msg:
                raise InsufficientFundsError(f"Insufficient funds: {e}")
            elif "invalid" in error_msg:
                raise InvalidOrderError(f"Invalid order: {e}")
            else:
                raise OrderError(f"Failed to submit order: {e}")

    async def cancel_order(self, order_id: str) -> Order:
        """Cancel an order.

        Args:
            order_id: Broker order ID to cancel.

        Returns:
            Updated order with cancelled status.
        """
        self._require_connection()

        try:
            if order_id not in self._order_map:
                raise OrderError(f"Order {order_id} not found")

            trade, contract = self._order_map[order_id]
            self._ib.cancelOrder(trade.order)

            # Wait for cancellation
            await asyncio.sleep(0.5)

            return self._convert_trade_to_order(trade, contract)

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

        Note: IBKR modifies orders in place rather than creating new ones.
        """
        self._require_connection()

        try:
            if order_id not in self._order_map:
                raise OrderError(f"Order {order_id} not found")

            trade, contract = self._order_map[order_id]
            ib_order = trade.order

            # Modify order fields
            if quantity is not None:
                ib_order.totalQuantity = float(quantity)
            if limit_price is not None and hasattr(ib_order, 'lmtPrice'):
                ib_order.lmtPrice = float(limit_price)
            if stop_price is not None and hasattr(ib_order, 'auxPrice'):
                ib_order.auxPrice = float(stop_price)
            if time_in_force is not None:
                ib_order.tif = self._map_time_in_force(time_in_force)

            # Submit modified order
            trade = self._ib.placeOrder(contract, ib_order)
            await asyncio.sleep(0.5)

            return self._convert_trade_to_order(trade, contract)

        except Exception as e:
            raise OrderError(f"Failed to replace order {order_id}: {e}")

    async def get_order(self, order_id: str) -> Order:
        """Get order by ID.

        Args:
            order_id: Broker order ID.

        Returns:
            Order details.
        """
        self._require_connection()

        if order_id not in self._order_map:
            raise OrderError(f"Order {order_id} not found")

        trade, contract = self._order_map[order_id]
        return self._convert_trade_to_order(trade, contract)

    async def get_orders(
        self,
        status: Optional[OrderStatus] = None,
        limit: int = 100,
        symbols: Optional[List[str]] = None,
    ) -> List[Order]:
        """Get orders with optional filters.

        Args:
            status: Filter by order status.
            limit: Maximum number of orders.
            symbols: Filter by symbols.

        Returns:
            List of orders.
        """
        self._require_connection()

        try:
            orders = []
            for order_id, (trade, contract) in self._order_map.items():
                order = self._convert_trade_to_order(trade, contract)

                # Apply filters
                if status and order.status != status:
                    continue
                if symbols and order.symbol not in symbols:
                    continue

                orders.append(order)

                if len(orders) >= limit:
                    break

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
            portfolio = self._ib.portfolio()

            positions = []
            for item in portfolio:
                if item.position == 0:
                    continue

                # Determine asset class
                contract = item.contract
                if hasattr(contract, 'secType'):
                    if contract.secType == "FUT":
                        asset_class = AssetClass.FUTURE
                    elif contract.secType == "OPT":
                        asset_class = AssetClass.OPTION
                    elif contract.secType == "CASH":
                        asset_class = AssetClass.FOREX
                    else:
                        asset_class = AssetClass.EQUITY
                else:
                    asset_class = AssetClass.EQUITY

                position = Position(
                    symbol=contract.symbol,
                    quantity=Decimal(str(abs(item.position))),
                    side=PositionSide.LONG if item.position > 0 else PositionSide.SHORT,
                    avg_entry_price=Decimal(str(item.averageCost or 0)),
                    current_price=Decimal(str(item.marketPrice or 0)),
                    market_value=Decimal(str(item.marketValue or 0)),
                    cost_basis=Decimal(str(abs(item.position * (item.averageCost or 0)))),
                    unrealized_pnl=Decimal(str(item.unrealizedPNL or 0)),
                    unrealized_pnl_percent=Decimal("0"),  # Would need to calculate
                    asset_class=asset_class,
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
        positions = await self.get_positions()
        for position in positions:
            if position.symbol == symbol:
                return position
        return None

    async def get_quote(self, symbol: str) -> Quote:
        """Get current quote for a symbol.

        Args:
            symbol: Symbol to get quote for.

        Returns:
            Current quote data.
        """
        self._require_connection()

        try:
            contract = self._create_contract(symbol)

            # Qualify contract
            qualified = await self._ib.qualifyContractsAsync(contract)
            if not qualified:
                raise BrokerError(f"Failed to qualify contract for {symbol}")
            contract = qualified[0]

            # Request market data
            ticker = self._ib.reqMktData(contract, "", False, False)
            await asyncio.sleep(1)  # Wait for data

            return Quote(
                symbol=symbol,
                bid_price=Decimal(str(ticker.bid)) if ticker.bid else None,
                ask_price=Decimal(str(ticker.ask)) if ticker.ask else None,
                last_price=Decimal(str(ticker.last)) if ticker.last else None,
                bid_size=ticker.bidSize,
                ask_size=ticker.askSize,
                volume=ticker.volume,
                timestamp=datetime.now(timezone.utc),
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
            contract = self._create_contract(symbol)

            # Qualify to get full details
            qualified = await self._ib.qualifyContractsAsync(contract)
            if not qualified:
                raise BrokerError(f"Failed to qualify contract for {symbol}")
            contract = qualified[0]

            # Determine asset class
            sec_type = getattr(contract, 'secType', 'STK')
            if sec_type == "FUT":
                asset_class = AssetClass.FUTURE
            elif sec_type == "OPT":
                asset_class = AssetClass.OPTION
            elif sec_type == "CASH":
                asset_class = AssetClass.FOREX
            elif sec_type == "ETF":
                asset_class = AssetClass.ETF
            else:
                asset_class = AssetClass.EQUITY

            return AssetInfo(
                symbol=symbol,
                name=getattr(contract, 'localSymbol', symbol),
                asset_class=asset_class,
                exchange=contract.exchange,
                tradable=True,
                shortable=True,  # Would need to check
                marginable=True,  # Would need to check
            )

        except Exception as e:
            raise BrokerError(f"Failed to get asset info for {symbol}: {e}")


# Export
__all__ = ["IBKRBroker", "IB_INSYNC_AVAILABLE", "FUTURES_SPECS"]
