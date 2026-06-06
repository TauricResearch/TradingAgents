"""Submit orders to a broker and reconcile their state.

Bridges the deterministic Trade rows with the broker abstraction. Submission is
idempotent (client_order_id); reconciliation re-reads the broker as the source
of truth, which is exactly the graceful-recovery routine from the wiki.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..broker.base import Broker, OrderRequest
from ..domain.state import ResearchState
from ..storage.models import Trade
from .trade import propose_and_record

# Broker order states that are not yet final -> candidates for reconciliation.
_OPEN_STATUSES = ("pending", "accepted")


def submit_trade(session: Session, trade: Trade, broker: Broker) -> Trade:
    """Send a persisted (pending) trade to the broker and record the outcome."""
    req = OrderRequest(
        symbol=trade.symbol,
        side=trade.action,
        quantity=trade.quantity or 0.0,
        order_type="limit" if trade.entry_price is not None else "market",
        limit_price=trade.entry_price,
        stop_loss=trade.stop_loss,
        take_profit=trade.take_profit,
        client_order_id=trade.client_order_id,
        asset_type=trade.asset_type,
        option_type=trade.option_type,
    )
    order = broker.submit_order(req)
    trade.broker_order_id = order.broker_order_id
    trade.status = order.status.value
    session.flush()
    return trade


def execute_thesis(
    session: Session, state: ResearchState, broker: Broker, **sizing: Any
) -> Trade:
    """End-to-end: size + record the order, then submit it to the broker."""
    trade = propose_and_record(session, state, **sizing)
    return submit_trade(session, trade, broker)


def reconcile_open_trades(session: Session, broker: Broker) -> list[Trade]:
    """Re-read the broker for every non-final trade; align the DB to it.

    Broker is the source of truth (graceful recovery). Returns the trades whose
    status/broker id changed.
    """
    open_trades = list(
        session.scalars(
            select(Trade).where(
                Trade.status.in_(_OPEN_STATUSES),
                Trade.client_order_id.is_not(None),
            )
        )
    )
    updated: list[Trade] = []
    for trade in open_trades:
        order = broker.get_order(trade.client_order_id)
        if order is None:
            continue
        if order.status.value != trade.status or order.broker_order_id != trade.broker_order_id:
            trade.status = order.status.value
            trade.broker_order_id = order.broker_order_id
            updated.append(trade)
    session.flush()
    return updated
