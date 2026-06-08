"""Portfolio performance vs benchmark (alpha).

Compares the portfolio's total-value return against each configured benchmark's
return over the same period. The number to beat is the benchmark; alpha is how
much we beat it by. Feeds the cycle report and the future read-only dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

from .benchmark import benchmark_return
from .storage import repository as repo


@dataclass
class PerformanceReport:
    portfolio_return: Optional[float] = None
    benchmark_returns: dict[str, Optional[float]] = field(default_factory=dict)
    alpha: dict[str, Optional[float]] = field(default_factory=dict)


def portfolio_return(session: Session, *, since=None) -> Optional[float]:
    """Total-value return of the portfolio since ``since`` (or full history)."""
    first = repo.first_portfolio_snapshot_on_or_after(session, since)
    last = repo.latest_portfolio_snapshot(session)
    if first is None or last is None or not first.total_value:
        return None
    return last.total_value / first.total_value - 1.0


def performance_vs_benchmarks(
    session: Session, benchmark_symbols: list[str], *, since=None
) -> PerformanceReport:
    """Compute portfolio return, each benchmark's return, and alpha vs each."""
    pr = portfolio_return(session, since=since)
    report = PerformanceReport(portfolio_return=pr)
    for symbol in benchmark_symbols:
        br = benchmark_return(session, symbol, since=since)
        report.benchmark_returns[symbol] = br
        report.alpha[symbol] = (pr - br) if (pr is not None and br is not None) else None
    return report
