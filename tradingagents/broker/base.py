"""Broker interface and shared value objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Protocol, runtime_checkable


class OrderStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    FILLED = "filled"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


@dataclass
class OrderRequest:
    symbol: str
    side: str  # "buy" | "sell"
    quantity: float
    order_type: str = "limit"  # "market" | "limit"
    limit_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    client_order_id: Optional[str] = None


@dataclass
class BrokerOrder:
    client_order_id: str
    broker_order_id: Optional[str]
    status: OrderStatus
    symbol: str
    side: str
    quantity: float
    filled_quantity: float = 0.0
    filled_avg_price: Optional[float] = None
    raw: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Broker(Protocol):
    """Minimal interface every broker adapter implements."""

    def submit_order(self, req: OrderRequest) -> BrokerOrder: ...

    def get_order(self, client_order_id: str) -> Optional[BrokerOrder]: ...

    def get_positions(self) -> list[dict[str, Any]]: ...

    def get_account(self) -> dict[str, Any]: ...
