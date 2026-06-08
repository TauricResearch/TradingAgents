"""Portfolio-level risk gate (the Director's Statute, on the whole book).

Per-ticker risk lives in the Risk Analyst inside each evaluator. This is the
*aggregate* layer the single ticker can't see: admit proposed buys one by one
only while the whole portfolio stays within the Statute — 10% cash reserve,
total open risk (heat/VaR), and per-sector concentration. Deterministic;
the Director may add a qualitative Risk-Analyst opinion on top.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy.orm import Session

from ..storage import repository as repo


@dataclass
class PortfolioProposal:
    symbol: str
    position_value: float      # cash the buy consumes
    risk_value: float          # euro at risk (entry-stop)*qty
    sector: Optional[str] = None


@dataclass
class PortfolioRiskResult:
    admitted: list[str] = field(default_factory=list)
    blocked: dict[str, str] = field(default_factory=dict)  # symbol -> reason


def admit_within_statute(
    session: Session,
    proposals: list[PortfolioProposal],
    *,
    charter: Optional[dict[str, Any]] = None,
) -> PortfolioRiskResult:
    """Greedily admit buys (highest risk-adjusted first) keeping the book legal.

    Stops admitting a proposal if it would breach the cash reserve, the total
    risk cap, or a sector cap. Returns admitted symbols + blocked reasons.
    """
    charter = charter or {}
    reserve_pct = charter.get("cash_reserve_pct", 0.10)
    max_var = charter.get("max_portfolio_var", 0.10)
    max_sector = charter.get("max_sector_pct", 0.30)

    snap = repo.latest_portfolio_snapshot(session)
    cash = float(snap.cash) if snap else 0.0
    total = float(snap.total_value) if snap and snap.total_value else 0.0

    # Open risk already on the book = sum (entry-stop)*qty over filled longs.
    open_risk = 0.0
    for t in repo.open_trades(session):
        if t.entry_price is not None and t.stop_loss is not None and t.quantity:
            open_risk += abs(t.entry_price - t.stop_loss) * t.quantity

    sector_value = repo.sector_exposure(session)  # fraction per sector
    sector_value = {k: v * total for k, v in sector_value.items()} if total else {}

    result = PortfolioRiskResult()
    # Strongest first (smaller risk per euro of value -> better) is hard without
    # conviction here; keep input order (Director can pre-sort).
    for p in proposals:
        new_cash = cash - p.position_value
        if total > 0 and new_cash < reserve_pct * total:
            result.blocked[p.symbol] = "cash_reserve"
            continue
        new_var = ((open_risk + p.risk_value) / total) if total else 0.0
        if new_var > max_var:
            result.blocked[p.symbol] = "portfolio_var"
            continue
        sec = p.sector or "unknown"
        new_sec = (sector_value.get(sec, 0.0) + p.position_value) / total if total else 0.0
        if new_sec > max_sector:
            result.blocked[p.symbol] = "sector_concentration"
            continue
        # admit: commit its effect to the running totals
        cash = new_cash
        open_risk += p.risk_value
        sector_value[sec] = sector_value.get(sec, 0.0) + p.position_value
        result.admitted.append(p.symbol)
    return result
