"""
Base execution provider interface.

All execution providers must implement these methods to ensure
consistent order execution across different markets.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

# Optional sandbox for safe derivatives pricing code (derivatives_analyst)
try:
    from .sandbox import run_in_sandbox  # noqa: F401
except ImportError:
    run_in_sandbox = None  # type: ignore


class OrderSide(str, Enum):
    """Order side."""
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    """Order type."""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(str, Enum):
    """Order status."""
    PENDING = "pending"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class OrderRequest(BaseModel):
    """Order execution request."""
    symbol: str = Field(description="Trading symbol (e.g., 'BTC/USDT', 'AAPL')")
    side: OrderSide = Field(description="Buy or sell")
    order_type: OrderType = Field(description="Order type")
    quantity: float = Field(description="Order quantity")
    price: float | None = Field(default=None, description="Limit price")
    stop_price: float | None = Field(default=None, description="Stop price")
    time_in_force: str = Field(default="GTC", description="Time in force (GTC, IOC, FOK)")
    metadata: dict = Field(default_factory=dict, description="Additional metadata")


class OrderResult(BaseModel):
    """Order execution result."""
    order_id: str = Field(description="Exchange order ID")
    symbol: str = Field(description="Trading symbol")
    side: OrderSide = Field(description="Order side")
    order_type: OrderType = Field(description="Order type")
    quantity: float = Field(description="Ordered quantity")
    filled_quantity: float = Field(description="Filled quantity")
    price: float | None = Field(default=None, description="Average fill price")
    status: OrderStatus = Field(description="Order status")
    timestamp: datetime = Field(default_factory=datetime.now, description="Execution timestamp")
    fees: float = Field(default=0.0, description="Trading fees")
    metadata: dict = Field(default_factory=dict, description="Additional metadata")


class ExecutionProvider(ABC):
    """Abstract base class for all execution providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g., 'ccxt', 'hummingbot', 'lumibot')."""
        pass

    @property
    @abstractmethod
    def supported_markets(self) -> list[str]:
        """List of supported markets (e.g., ['CRYPTO', 'US', 'GLOBAL'])."""
        pass

    @abstractmethod
    def connect(self, credentials: dict) -> bool:
        """
        Connect to the exchange/broker.

        Args:
            credentials: API keys and secrets

        Returns:
            True if connected successfully
        """
        pass

    @abstractmethod
    def disconnect(self):
        """Disconnect from the exchange/broker."""
        pass

    @abstractmethod
    def get_balance(self) -> dict[str, float]:
        """
        Get account balance.

        Returns:
            Dict mapping asset to balance
        """
        pass

    @abstractmethod
    def get_position(self, symbol: str) -> Optional[dict]:
        """
        Get current position for a symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Position info or None
        """
        pass

    @abstractmethod
    def place_order(self, request: OrderRequest) -> OrderResult:
        """
        Place an order.

        Args:
            request: Order request

        Returns:
            Order result
        """
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order.

        Args:
            order_id: Order ID to cancel

        Returns:
            True if cancelled successfully
        """
        pass

    @abstractmethod
    def get_order_status(self, order_id: str) -> Optional[OrderResult]:
        """
        Get order status.

        Args:
            order_id: Order ID

        Returns:
            Order result or None
        """
        pass

    def has_market(self, market: str) -> bool:
        """Check if provider supports a specific market."""
        return market.upper() in [m.upper() for m in self.supported_markets]
