"""
Base broker interface for trading integrations.

This module defines the abstract interface that all broker implementations
must follow, ensuring consistency across different platforms.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime
from typing import List, Dict, Optional
from enum import Enum


class OrderSide(Enum):
    """Order side enumeration."""
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    """Order type enumeration."""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(Enum):
    """Order status enumeration."""
    PENDING = "pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass
class BrokerOrder:
    """Represents an order with a broker."""
    symbol: str
    side: OrderSide
    quantity: Decimal
    order_type: OrderType
    limit_price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    time_in_force: str = "day"  # day, gtc, ioc, fok
    order_id: Optional[str] = None
    status: OrderStatus = OrderStatus.PENDING
    filled_qty: Decimal = Decimal('0')
    filled_price: Optional[Decimal] = None
    submitted_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None


@dataclass
class BrokerPosition:
    """Represents a position held with a broker."""
    symbol: str
    quantity: Decimal
    avg_entry_price: Decimal
    current_price: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_percent: Decimal
    cost_basis: Decimal


@dataclass
class BrokerAccount:
    """Represents account information from a broker."""
    account_number: str
    cash: Decimal
    buying_power: Decimal
    portfolio_value: Decimal
    equity: Decimal
    last_equity: Decimal
    multiplier: Decimal
    currency: str = "USD"
    pattern_day_trader: bool = False


class BaseBroker(ABC):
    """
    Abstract base class for broker integrations.

    All broker implementations must inherit from this class and implement
    the abstract methods.
    """

    def __init__(self, paper_trading: bool = True):
        """
        Initialize broker connection.

        Args:
            paper_trading: Whether to use paper trading mode
        """
        self.paper_trading = paper_trading

    @abstractmethod
    def connect(self) -> bool:
        """
        Connect to the broker.

        Returns:
            True if connection successful, False otherwise
        """
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from the broker."""
        pass

    @abstractmethod
    def get_account(self) -> BrokerAccount:
        """
        Get account information.

        Returns:
            BrokerAccount object with current account info
        """
        pass

    @abstractmethod
    def get_positions(self) -> List[BrokerPosition]:
        """
        Get all current positions.

        Returns:
            List of BrokerPosition objects
        """
        pass

    @abstractmethod
    def get_position(self, symbol: str) -> Optional[BrokerPosition]:
        """
        Get position for a specific symbol.

        Args:
            symbol: Stock ticker symbol

        Returns:
            BrokerPosition if position exists, None otherwise
        """
        pass

    @abstractmethod
    def submit_order(self, order: BrokerOrder) -> BrokerOrder:
        """
        Submit an order to the broker.

        Args:
            order: BrokerOrder to submit

        Returns:
            BrokerOrder with updated status and order_id

        Raises:
            BrokerError: If order submission fails
        """
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order.

        Args:
            order_id: ID of the order to cancel

        Returns:
            True if cancellation successful, False otherwise
        """
        pass

    @abstractmethod
    def get_order(self, order_id: str) -> Optional[BrokerOrder]:
        """
        Get order status.

        Args:
            order_id: ID of the order

        Returns:
            BrokerOrder if found, None otherwise
        """
        pass

    @abstractmethod
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
        pass

    @abstractmethod
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
        pass

    def buy_market(
        self,
        symbol: str,
        quantity: Decimal,
        time_in_force: str = "day"
    ) -> BrokerOrder:
        """
        Convenience method to submit a market buy order.

        Args:
            symbol: Stock ticker
            quantity: Number of shares
            time_in_force: Order duration

        Returns:
            Submitted BrokerOrder
        """
        order = BrokerOrder(
            symbol=symbol,
            side=OrderSide.BUY,
            quantity=quantity,
            order_type=OrderType.MARKET,
            time_in_force=time_in_force
        )
        return self.submit_order(order)

    def sell_market(
        self,
        symbol: str,
        quantity: Decimal,
        time_in_force: str = "day"
    ) -> BrokerOrder:
        """
        Convenience method to submit a market sell order.

        Args:
            symbol: Stock ticker
            quantity: Number of shares
            time_in_force: Order duration

        Returns:
            Submitted BrokerOrder
        """
        order = BrokerOrder(
            symbol=symbol,
            side=OrderSide.SELL,
            quantity=quantity,
            order_type=OrderType.MARKET,
            time_in_force=time_in_force
        )
        return self.submit_order(order)

    def buy_limit(
        self,
        symbol: str,
        quantity: Decimal,
        limit_price: Decimal,
        time_in_force: str = "day"
    ) -> BrokerOrder:
        """
        Convenience method to submit a limit buy order.

        Args:
            symbol: Stock ticker
            quantity: Number of shares
            limit_price: Maximum price to pay
            time_in_force: Order duration

        Returns:
            Submitted BrokerOrder
        """
        order = BrokerOrder(
            symbol=symbol,
            side=OrderSide.BUY,
            quantity=quantity,
            order_type=OrderType.LIMIT,
            limit_price=limit_price,
            time_in_force=time_in_force
        )
        return self.submit_order(order)

    def sell_limit(
        self,
        symbol: str,
        quantity: Decimal,
        limit_price: Decimal,
        time_in_force: str = "day"
    ) -> BrokerOrder:
        """
        Convenience method to submit a limit sell order.

        Args:
            symbol: Stock ticker
            quantity: Number of shares
            limit_price: Minimum price to accept
            time_in_force: Order duration

        Returns:
            Submitted BrokerOrder
        """
        order = BrokerOrder(
            symbol=symbol,
            side=OrderSide.SELL,
            quantity=quantity,
            order_type=OrderType.LIMIT,
            limit_price=limit_price,
            time_in_force=time_in_force
        )
        return self.submit_order(order)


class BrokerError(Exception):
    """Base exception for broker-related errors."""
    pass


class BrokerConnectionError(BrokerError):
    """Raised when broker connection fails."""
    pass


class OrderError(BrokerError):
    """Raised when order submission/management fails."""
    pass


class InsufficientFundsError(BrokerError):
    """Raised when account has insufficient funds."""
    pass
