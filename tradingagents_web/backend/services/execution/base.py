"""BaseTraderInterface — all broker implementations (simulation, live) must implement this."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class OrderRequest:
    ticker: str
    action: str            # "BUY" | "SELL"
    quantity: float
    reference_price: float
    ai_signal: str = ""
    ai_reasoning: str = ""


@dataclass
class OrderResult:
    order_id: str
    status: str            # FILLED | PARTIALLY_FILLED | REJECTED
    filled_price: Optional[float]
    filled_quantity: Optional[float]
    commission: float = 0.0
    message: str = ""
    executed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class BaseTraderInterface(ABC):
    """
    Pluggable trader interface.

    To add a new broker, subclass this, implement all abstract methods,
    and register the class in services/execution/factory.py's _REGISTRY.
    """

    @abstractmethod
    def get_current_price(self, ticker: str) -> Optional[float]:
        """Return latest price for ticker, or None if unavailable."""
        ...

    @abstractmethod
    def place_order(self, request: OrderRequest) -> OrderResult:
        """Submit an order and return the execution result."""
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order. Returns True if successfully cancelled."""
        ...

    @abstractmethod
    def get_balance(self) -> float:
        """Return available cash balance."""
        ...

    @abstractmethod
    def get_positions(self) -> dict[str, dict]:
        """Return {ticker: {quantity, avg_buy_price, current_price}} for all open positions."""
        ...

    @property
    @abstractmethod
    def mode(self) -> str:
        """'simulation' or 'live'"""
        ...

    @property
    @abstractmethod
    def broker_name(self) -> str:
        """Human-readable broker name, e.g. 'simulation', 'binance'"""
        ...
