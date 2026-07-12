"""OMS order records: state machine, execution plans, closed trades.

The transition table is the single source of legality — an illegal
transition raises (and is audited by the caller) instead of silently
corrupting the book. Terminal states never transition again.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from tradingagents.contracts import utc_now
from tradingagents.pro.execution.interface import (
    BracketSpec,
    OrderSpec,
    OrderState,
    OrderUpdate,
)

_S = OrderState
LEGAL_TRANSITIONS: dict[OrderState, frozenset[OrderState]] = {
    _S.PENDING_SUBMIT: frozenset({_S.SUBMITTED, _S.ACKED, _S.PARTIALLY_FILLED,
                                  _S.FILLED, _S.REJECTED, _S.UNKNOWN,
                                  _S.ABANDONED}),
    _S.SUBMITTED: frozenset({_S.ACKED, _S.PARTIALLY_FILLED, _S.FILLED,
                             _S.CANCELED, _S.REJECTED, _S.UNKNOWN}),
    _S.ACKED: frozenset({_S.PARTIALLY_FILLED, _S.FILLED, _S.CANCELED,
                         _S.REJECTED, _S.UNKNOWN}),
    _S.PARTIALLY_FILLED: frozenset({_S.PARTIALLY_FILLED, _S.FILLED,
                                    _S.CANCELED, _S.UNKNOWN}),
    _S.UNKNOWN: frozenset({_S.SUBMITTED, _S.ACKED, _S.PARTIALLY_FILLED,
                           _S.FILLED, _S.CANCELED, _S.REJECTED,
                           _S.ABANDONED}),
    # terminal states transition nowhere
    _S.FILLED: frozenset(),
    _S.CANCELED: frozenset(),
    _S.REJECTED: frozenset(),
    _S.ABANDONED: frozenset(),
}


class IllegalTransition(Exception):
    pass


@dataclass
class ManagedOrder:
    """Mutable OMS record for one venue order (one leg)."""

    spec: OrderSpec
    leg: str = "entry"            # entry | sl | tpN | flatten
    state: OrderState = OrderState.PENDING_SUBMIT
    venue_order_id: str = ""
    filled_quantity: float = 0.0
    avg_fill_price: float = 0.0
    commission: float = 0.0
    reason: str = ""
    bracket_group: str = ""       # shared key linking entry + protections
    sent: bool = False            # journaled "submitting" reached the wire
    updated_at: datetime = field(default_factory=utc_now)

    @property
    def client_order_id(self) -> str:
        return self.spec.client_order_id

    def apply(self, update: OrderUpdate) -> bool:
        """Advance to the update's state; returns True if anything changed.
        Same-state fill progress (partial fills) is a legal self-update."""
        if update.state == self.state:
            changed = (update.filled_quantity != self.filled_quantity
                       or update.venue_order_id not in ("", self.venue_order_id))
            self._absorb(update)
            return changed
        if update.state not in LEGAL_TRANSITIONS[self.state]:
            raise IllegalTransition(
                f"{self.client_order_id}: {self.state.value} -> "
                f"{update.state.value}"
            )
        self.state = update.state
        self._absorb(update)
        return True

    def _absorb(self, update: OrderUpdate) -> None:
        if update.venue_order_id:
            self.venue_order_id = update.venue_order_id
        if update.filled_quantity:
            self.filled_quantity = update.filled_quantity
        if update.avg_fill_price:
            self.avg_fill_price = update.avg_fill_price
        if update.commission:
            self.commission = update.commission
        if update.reason:
            self.reason = update.reason
        self.updated_at = update.ts


@dataclass(frozen=True)
class ExecutionPlan:
    """Entry + protection derived from a gated recommendation. Built by the
    router; the OMS never sees LLM output, only this deterministic object."""

    run_id: str
    decision_hash: str
    symbol: str
    side: Literal["BUY", "SELL"]
    quantity: float
    reference_price: float
    bracket: BracketSpec | None = None
    protection_mode: Literal["bar_close", "venue_bracket"] = "bar_close"


@dataclass(frozen=True)
class ClosedTrade:
    """Realized exit detected by the OMS (venue-side protection or
    flatten) — feeds the SAME downstream as bar-close exits."""

    symbol: str
    quantity: float
    entry_price: float
    exit_price: float
    pnl: float
    commission: float
    reason: str                  # stop_loss | take_profit | flatten
    client_order_id: str = ""
    closed_at: datetime = field(default_factory=utc_now)
