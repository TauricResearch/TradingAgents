"""Abstract broker interface and shared data models."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(str, Enum):
    PENDING = "pending"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class AccountInfo:
    cash: float
    portfolio_value: float
    buying_power: float
    equity: float
    daytrade_count: int = 0


@dataclass
class Position:
    ticker: str
    qty: float
    avg_entry_price: float
    current_price: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    side: str = "long"


@dataclass
class Order:
    order_id: str
    ticker: str
    side: OrderSide
    qty: float
    order_type: OrderType
    status: OrderStatus
    submitted_at: datetime
    filled_qty: float = 0.0
    filled_avg_price: Optional[float] = None
    filled_at: Optional[datetime] = None
    limit_price: Optional[float] = None
    reject_reason: Optional[str] = None


class BrokerAdapter(ABC):
    """
    Abstract interface every broker implementation must satisfy.

    Concrete implementations (Alpaca, IBKR, mock) plug in here so the
    rest of the system never imports broker-specific code directly.
    """

    # ------------------------------------------------------------------ #
    # Account                                                              #
    # ------------------------------------------------------------------ #

    @abstractmethod
    def get_account(self) -> AccountInfo:
        """Return current account balances and buying power."""

    # ------------------------------------------------------------------ #
    # Positions                                                            #
    # ------------------------------------------------------------------ #

    @abstractmethod
    def get_positions(self) -> List[Position]:
        """Return all open positions."""

    @abstractmethod
    def get_position(self, ticker: str) -> Optional[Position]:
        """Return the open position for *ticker*, or None if flat."""

    # ------------------------------------------------------------------ #
    # Orders                                                               #
    # ------------------------------------------------------------------ #

    @abstractmethod
    def submit_order(
        self,
        ticker: str,
        qty: float,
        side: OrderSide,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Optional[float] = None,
        time_in_force: str = "day",
    ) -> Order:
        """
        Submit an order.

        Args:
            ticker: Ticker symbol (e.g. "AAPL").
            qty: Number of shares (fractional shares supported where available).
            side: BUY or SELL.
            order_type: MARKET or LIMIT.
            limit_price: Required when order_type is LIMIT.
            time_in_force: "day", "gtc", "ioc", "fok".

        Returns:
            Order object with the broker-assigned order_id and initial status.
        """

    @abstractmethod
    def get_order(self, order_id: str) -> Order:
        """Fetch the current state of an order by ID."""

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order. Returns True if cancelled successfully."""

    @abstractmethod
    def get_order_history(self, limit: int = 100) -> List[Order]:
        """Return recent filled/cancelled orders, newest first."""

    # ------------------------------------------------------------------ #
    # Market data (lightweight — full data comes from TradingAgents)       #
    # ------------------------------------------------------------------ #

    @abstractmethod
    def get_latest_price(self, ticker: str) -> float:
        """Return the latest trade price for *ticker*."""

    # ------------------------------------------------------------------ #
    # Convenience helpers (implemented on the base class)                  #
    # ------------------------------------------------------------------ #

    def close_position(self, ticker: str) -> Optional[Order]:
        """
        Fully close an open position in *ticker*.
        Returns the resulting sell order, or None if no position exists.
        """
        pos = self.get_position(ticker)
        if pos is None:
            return None
        return self.submit_order(
            ticker=ticker,
            qty=pos.qty,
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
        )

    def is_market_open(self) -> bool:
        """Return True if the market is currently in normal trading hours."""
        import pytz
        now = datetime.now(pytz.timezone("America/New_York"))
        # Monday=0 … Friday=4
        if now.weekday() >= 5:
            return False
        market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
        return market_open <= now < market_close
