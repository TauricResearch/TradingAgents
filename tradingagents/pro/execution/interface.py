"""The single execution interface every venue adapter implements.

Adapters are dumb pipes: they submit validated orders and report state.
All judgment (validation, kill switch, circuit breakers, retries,
reconciliation, audit) lives in the router, so a new venue is a VenueSpec
plus transport code — never a re-implementation of safety logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol

from tradingagents.contracts import utc_now


class AdapterError(Exception):
    """Transient adapter failure — the router may retry with the same
    idempotency key."""


class ExecutionNotEnabled(Exception):
    """Raised by live transport stubs: Phase 9 ships paper-only
    (Constraint 5)."""


@dataclass(frozen=True)
class OrderRequest:
    idempotency_key: str  # recommendation id (+leg); resubmits must not double-fill
    symbol: str  # canonical symbol; adapter maps to venue convention
    side: Literal["BUY", "SELL"]
    quantity: float
    reference_price: float  # engine's entry reference; paper fills anchor here
    stop_loss: float | None = None
    take_profits: tuple[float, ...] = ()
    created_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class OrderResult:
    status: Literal["filled", "rejected", "duplicate"]
    idempotency_key: str
    venue: str
    venue_symbol: str = ""
    filled_quantity: float = 0.0
    fill_price: float = 0.0
    commission: float = 0.0
    reason: str = ""


@dataclass(frozen=True)
class BrokerPosition:
    symbol: str  # canonical
    side: Literal["BUY", "SELL"]
    quantity: float
    avg_price: float


@dataclass(frozen=True)
class AccountState:
    venue: str
    equity: float
    cash: float
    positions: tuple[BrokerPosition, ...] = ()


class ExecutionAdapter(Protocol):
    name: str

    def submit(self, order: OrderRequest) -> OrderResult: ...

    def close_position(self, symbol: str, reference_price: float) -> OrderResult: ...

    def positions(self) -> list[BrokerPosition]: ...

    def account(self) -> AccountState: ...
