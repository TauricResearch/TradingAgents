"""Exit management: close open positions on stop-loss / take-profit.

The deterministic side of the trade lifecycle. Each cycle, before opening new
positions, we manage what we already hold: if the latest price breached the
stop or the target, submit a closing order and stamp the exit_reason. This also
feeds the learning loop (closed trades = outcomes to match against the thesis).

Rating-based disinvestment (selling a weak holding to free room for a stronger
conviction) is a documented follow-up.
"""

from __future__ import annotations

from typing import Callable, Optional

from sqlalchemy.orm import Session

from ..broker.base import Broker, OrderRequest
from ..storage import repository as repo
from ..storage.models import Trade


def _latest_close(session: Session, symbol: str) -> Optional[float]:
    bar = repo.latest_price(session, symbol)
    return bar.close if bar is not None else None


def manage_exits(
    session: Session,
    broker: Broker,
    *,
    price_fn: Callable[[Session, str], Optional[float]] = _latest_close,
) -> list[Trade]:
    """Close open positions whose stop or target was hit. Returns closed trades."""
    closed: list[Trade] = []
    for trade in repo.open_trades(session):
        price = price_fn(session, trade.symbol)
        if price is None:
            continue

        reason: Optional[str] = None
        if trade.stop_loss is not None and price <= trade.stop_loss:
            reason = "sl"
        elif trade.take_profit is not None and price >= trade.take_profit:
            reason = "tp"
        if reason is None:
            continue

        # Submit the closing order (idempotent on the derived client_order_id).
        coid = f"{trade.client_order_id}-exit" if trade.client_order_id else None
        broker.submit_order(
            OrderRequest(
                symbol=trade.symbol,
                side="sell",
                quantity=trade.quantity or 0.0,
                order_type="market",
                client_order_id=coid,
            )
        )
        trade.status = "closed"
        trade.exit_reason = reason
        session.flush()
        closed.append(trade)
    return closed
