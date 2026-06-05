"""Deterministic Trade function: approved thesis -> concrete order.

No LLM here. The thesis already carries the direction, the ATR-derived price
levels and the sizing inputs; this module computes the quantity with the risk
engine and records the order with an idempotent client_order_id.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy.orm import Session

from ..domain.risk import SizingResult, position_size
from ..domain.state import ResearchState
from ..storage import repository as repo
from ..storage.models import Trade


@dataclass
class OrderProposal:
    symbol: str
    action: str  # "buy" | "sell"
    quantity: float
    entry_price: float
    stop_loss: float
    take_profit: float
    client_order_id: str
    sizing: SizingResult


def can_trade(state: ResearchState) -> bool:
    """A thesis is executable only if approved, complete, actionable and priced."""
    return (
        state.is_approved
        and state.is_complete()
        and state.direction is not None
        and state.direction.is_actionable
        and state.levels is not None
        and state.levels.has_prices
    )


def build_trade(
    state: ResearchState,
    portfolio_value: float,
    *,
    base_risk_pct: float = 0.01,
    heat_used_pct: float = 0.0,
    heat_max_pct: float = 0.06,
    max_position_pct: float = 0.10,
    client_order_id: Optional[str] = None,
) -> OrderProposal:
    """Translate an approved investment_state into an order proposal."""
    if not can_trade(state):
        raise ValueError(
            "build_trade requires an approved, complete, actionable, priced thesis"
        )
    assert state.levels is not None and state.direction is not None
    lv = state.levels
    stop_distance = abs(lv.entry_price - lv.stop_loss)  # = k_stop · ATR
    sizing = position_size(
        portfolio_value,
        lv.entry_price,
        stop_distance,
        state.direction,
        base_risk_pct=base_risk_pct,
        heat_used_pct=heat_used_pct,
        heat_max_pct=heat_max_pct,
        max_position_pct=max_position_pct,
    )
    action = "buy" if state.direction.is_long else "sell"
    coid = client_order_id or f"{state.ticker}-{uuid.uuid4().hex[:12]}"
    return OrderProposal(
        symbol=state.ticker,
        action=action,
        quantity=sizing.quantity,
        entry_price=lv.entry_price,
        stop_loss=lv.stop_loss,
        take_profit=lv.take_profit,
        client_order_id=coid,
        sizing=sizing,
    )


def persist_trade(
    session: Session, proposal: OrderProposal, *, payload: Optional[dict[str, Any]] = None
) -> Trade:
    """Record the order as a pending trade (idempotent on client_order_id)."""
    return repo.record_trade(
        session,
        proposal.symbol,
        proposal.action,
        quantity=proposal.quantity,
        entry_price=proposal.entry_price,
        stop_loss=proposal.stop_loss,
        take_profit=proposal.take_profit,
        client_order_id=proposal.client_order_id,
        status="pending",
        payload=payload,
    )


def inject_portfolio_state(session: Session) -> dict[str, Any]:
    """Tool G: the current portfolio snapshot the agents reason against."""
    snap = repo.latest_portfolio_snapshot(session)
    if snap is None:
        return {"cash": 0.0, "total_value": 0.0, "positions": [], "pnl": None}
    return {
        "cash": snap.cash,
        "total_value": snap.total_value,
        "positions": snap.positions,
        "pnl": snap.pnl,
        "as_of": snap.ts.isoformat() if snap.ts else None,
    }


def propose_and_record(session: Session, state: ResearchState, **kwargs: Any) -> Trade:
    """End-to-end: read portfolio value, size the order, persist it.

    Uses the latest portfolio snapshot's ``total_value`` as the sizing base.
    Returns the persisted Trade.
    """
    portfolio = inject_portfolio_state(session)
    proposal = build_trade(state, portfolio["total_value"], **kwargs)
    return persist_trade(session, proposal, payload=state.seal())
