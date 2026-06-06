"""Rating-based disinvestment: free room by selling the weakest holdings.

The deterministic module the wiki calls for: when a high-conviction opportunity
needs cash and the portfolio is near the 10% reserve, sell the weakest existing
positions (lowest conviction, then lowest screening score) until enough room is
freed. No LLM — it ranks on the persisted scheda and closes deterministically.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from ..broker.base import Broker, OrderRequest
from ..storage import repository as repo
from ..storage.models import Trade

# Higher = stronger long conviction (weakest sorts first).
_CONV_RANK = {
    "strong_sell": 0, "sell": 1, "hold": 2, "buy": 3, "strong_buy": 4, None: 2,
}


def rank_holdings_by_weakness(session: Session) -> list[Trade]:
    """Open positions ordered weakest-first (conviction, then screening score)."""
    def key(t: Trade):
        card = repo.get_ticker_card(session, t.symbol)
        conv = _CONV_RANK.get(card.latest_conviction if card else None, 2)
        score = (card.screening_score if card and card.screening_score is not None else 0.0)
        return (conv, score)

    return sorted(repo.open_trades(session), key=key)


def disinvest_weakest(
    session: Session, broker: Broker, *, needed_cash: float, protect: Optional[set[str]] = None
) -> list[Trade]:
    """Close weakest holdings until ``needed_cash`` is freed. Returns closed trades."""
    protect = protect or set()
    freed = 0.0
    closed: list[Trade] = []
    for trade in rank_holdings_by_weakness(session):
        if freed >= needed_cash:
            break
        if trade.symbol in protect:
            continue
        coid = f"{trade.client_order_id}-disinvest" if trade.client_order_id else None
        broker.submit_order(
            OrderRequest(symbol=trade.symbol, side="sell", quantity=trade.quantity or 0.0,
                         order_type="market", client_order_id=coid)
        )
        trade.status = "closed"
        trade.exit_reason = "rating"
        session.flush()
        freed += (trade.entry_price or 0.0) * (trade.quantity or 0.0)
        closed.append(trade)
    return closed
