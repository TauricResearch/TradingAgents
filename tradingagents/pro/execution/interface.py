"""The single execution interface every venue adapter implements.

Adapters are dumb pipes: they submit validated orders and report state.
All judgment (validation, kill switch, circuit breakers, retries,
reconciliation, audit) lives in the router, so a new venue is a VenueSpec
plus transport code — never a re-implementation of safety logic.

Two generations coexist (go-live Phase 1):

- ``ExecutionAdapter`` — the original synchronous contract: ``submit``
  returns terminal truth. Paper mode and every pre-go-live test use it.
- ``VenueAdapter`` — the async-capable v2 contract for live venues:
  ``place_order`` returns the *furthest state reached synchronously*
  (paper: FILLED immediately; a real venue: ACKED, with fills arriving
  later via ``poll_updates``). The OMS (Phase 2) drives this protocol;
  the paper adapter implements both, so one conformance suite covers
  every implementation.
"""

from __future__ import annotations

import enum
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
    # "submitted" (v2 only): order is working on the venue, not terminal —
    # never produced by the synchronous paper path
    status: Literal["filled", "rejected", "duplicate", "submitted"]
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


# --- v2 contract (go-live) ----------------------------------------------------------


class OrderState(str, enum.Enum):
    PENDING_SUBMIT = "pending_submit"
    SUBMITTED = "submitted"
    ACKED = "acked"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    UNKNOWN = "unknown"
    # journaled intent provably never reached the venue; terminal, never
    # auto-resent (would otherwise pollute reject metrics or double-send)
    ABANDONED = "abandoned"

    @property
    def terminal(self) -> bool:
        return self in _TERMINAL_STATES


_TERMINAL_STATES = frozenset({
    OrderState.FILLED, OrderState.CANCELED,
    OrderState.REJECTED, OrderState.ABANDONED,
})


@dataclass(frozen=True)
class OrderSpec:
    """What to place. ``client_order_id`` is deterministic (Phase 2 ids.py)
    so a crash-and-resubmit dedupes venue-side."""

    client_order_id: str
    symbol: str  # canonical
    venue_symbol: str
    side: Literal["BUY", "SELL"]
    quantity: float
    order_type: Literal["market", "limit"] = "market"
    limit_price: float | None = None
    reduce_only: bool = False
    time_in_force: str = "gtc"
    reference_price: float = 0.0  # engine's reference; paper fills anchor here
    created_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class BracketSpec:
    """Protective orders attached to an entry (TP ladder + stop)."""

    stop_loss_price: float
    take_profits: tuple[tuple[float, float], ...] = ()  # (price, size_fraction)
    stop_trigger: Literal["mark", "last"] = "mark"


@dataclass(frozen=True)
class OrderUpdate:
    """The furthest known truth about one order, from any source (sync
    response, poll, stream). ``raw`` keeps the venue payload for audit."""

    client_order_id: str
    state: OrderState
    venue_order_id: str = ""
    filled_quantity: float = 0.0
    avg_fill_price: float = 0.0
    commission: float = 0.0
    reason: str = ""
    ts: datetime = field(default_factory=utc_now)
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class AdapterCapabilities:
    native_bracket: bool = False
    terminal_on_place: bool = False  # paper: orders go terminal synchronously
    supports_client_oid_lookup: bool = False
    supports_streams: bool = False


class VenueAdapter(Protocol):
    """v2 transport verbs. Implementations must be honest in
    ``capabilities()`` — the OMS branches on it (e.g. native brackets vs
    synthetic + watchdog)."""

    name: str

    def capabilities(self) -> AdapterCapabilities: ...

    def place_order(self, spec: OrderSpec,
                    bracket: BracketSpec | None = None) -> OrderUpdate: ...

    def cancel_order(self, client_order_id: str) -> OrderUpdate: ...

    def get_order(self, client_order_id: str) -> OrderUpdate | None: ...

    def open_orders(self) -> list[OrderUpdate]: ...

    def poll_updates(self, since: datetime) -> list[OrderUpdate]: ...

    def positions(self) -> list[BrokerPosition]: ...

    def account(self) -> AccountState: ...

    def supported_symbols(self) -> set[str]: ...
