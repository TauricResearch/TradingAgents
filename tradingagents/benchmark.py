"""Benchmark tracking — dynamic, never hardcoded.

The benchmark symbols come from config (`[benchmark] symbols`, a list that can
change over time); nothing here assumes SPY. We ingest the benchmark bars like
any other price series and expose their return over a period, so performance can
be compared (alpha).
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from sqlalchemy.orm import Session

from .ingestion import ingest_price_bars
from .ingestion.price_ingest import PriceFetcher
from .storage import repository as repo


def ingest_benchmarks(
    session: Session,
    symbols: list[str],
    *,
    fetcher: PriceFetcher,
    start: str,
    end: Optional[str] = None,
) -> None:
    """Refresh OHLCV for each configured benchmark symbol (few symbols, cheap)."""
    end = end or date.today().isoformat()
    for symbol in symbols:
        ingest_price_bars(session, symbol, fetcher=fetcher, start=start, end=end)


def benchmark_return(session: Session, symbol: str, *, since=None) -> Optional[float]:
    """Total return of a benchmark symbol since ``since`` (or all stored history)."""
    first = repo.first_price_on_or_after(session, symbol, since) if since else None
    if first is None:
        # no `since` (or nothing after it): use the earliest stored bar
        first = repo.first_price_on_or_after(session, symbol, date(1970, 1, 1))
    last = repo.latest_price(session, symbol)
    if first is None or last is None or not first.close:
        return None
    return last.close / first.close - 1.0
