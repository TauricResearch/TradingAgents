"""Mantainer: keep the rendicontazione (portfolio_state) up to date.

Canvas edge ``technical -> mantainer -> rendicontazione portafoglio``: a
non-LLM process that turns transactions/positions into the portfolio accounting
the agents read. It marks open positions to market and writes a fresh snapshot,
using the broker as the source of truth for cash/positions when available.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from ..broker.base import Broker
from ..storage import repository as repo
from ..storage.models import PortfolioSnapshot


def _latest_close(session: Session, symbol: str) -> Optional[float]:
    bar = repo.latest_price(session, symbol)
    return bar.close if bar is not None else None


def run_mantainer(session: Session, broker: Optional[Broker] = None) -> PortfolioSnapshot:
    """Recompute and persist the current portfolio snapshot.

    With a broker, cash + positions come from it (source of truth); otherwise
    positions are derived from open trades. Positions are marked to the latest
    stored price.
    """
    if broker is not None:
        account = broker.get_account()
        cash = float(account.get("cash", 0.0))
        raw_positions = broker.get_positions()
    else:
        prev = repo.latest_portfolio_snapshot(session)
        cash = float(prev.cash) if prev is not None else 0.0
        raw_positions = [
            {"symbol": t.symbol, "qty": t.quantity} for t in repo.open_trades(session)
        ]

    positions = []
    invested = 0.0
    for p in raw_positions:
        price = _latest_close(session, p["symbol"]) or 0.0
        value = price * float(p.get("qty", 0) or 0)
        invested += value
        positions.append({**p, "price": price, "value": value})

    total = cash + invested
    return repo.save_portfolio_snapshot(
        session, cash=cash, total_value=total, positions=positions
    )
