"""Portfolio tools: current open risk (portfolio heat)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..storage import repository as repo


def get_open_positions_risk(session: Session) -> dict[str, Any]:
    """Aggregate open risk (portfolio heat) across filled long positions.

    heat = sum( (entry - stop) * qty ) / total_value. Feeds the position-sizing
    heat cap so a new trade can't push aggregate risk past the Statute limit.
    """
    snap = repo.latest_portfolio_snapshot(session)
    total = float(snap.total_value) if snap is not None else 0.0
    open_risk = 0.0
    for t in repo.open_trades(session):
        if t.entry_price is not None and t.stop_loss is not None and t.quantity:
            open_risk += abs(t.entry_price - t.stop_loss) * t.quantity
    heat = open_risk / total if total > 0 else 0.0
    return {"open_risk": open_risk, "heat_pct": heat, "total_value": total}
