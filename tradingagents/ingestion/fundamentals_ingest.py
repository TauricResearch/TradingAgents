"""Fundamentals ingestion: vendor -> DB.

Feeds the Fundamentals desk (health, valuation, event risk). Fetch behind a
protocol for offline testing; ``YFinanceFundamentalsFetcher`` is the real adapter.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional, Protocol, runtime_checkable

from sqlalchemy.orm import Session

from ..storage import repository as repo
from ..storage.models import FundamentalSnapshot


@runtime_checkable
class FundamentalsFetcher(Protocol):
    def fetch(self, symbol: str) -> dict[str, Any]:
        """Return a flat dict of valuation/health metrics."""
        ...


def ingest_fundamentals(
    session: Session, symbol: str, *, fetcher: FundamentalsFetcher, vendor: Optional[str] = None
) -> Optional[FundamentalSnapshot]:
    metrics = fetcher.fetch(symbol)
    if not metrics:
        return None
    return repo.save_fundamentals(
        session, symbol, metrics, as_of=date.today(), vendor=vendor
    )


# Keys pulled from yfinance .info into our metrics dict.
_YF_KEYS = {
    "trailingPE": "pe_trailing",
    "forwardPE": "pe_forward",
    "priceToBook": "pb",
    "returnOnEquity": "roe",
    "profitMargins": "profit_margin",
    "debtToEquity": "debt_to_equity",
    "revenueGrowth": "revenue_growth",
    "marketCap": "market_cap",
}


class YFinanceFundamentalsFetcher:
    """Real adapter over yfinance .info. Network-bound (integration)."""

    def fetch(self, symbol: str) -> dict[str, Any]:
        import yfinance as yf

        info = getattr(yf.Ticker(symbol.upper()), "info", None) or {}
        return {ours: info[their] for their, ours in _YF_KEYS.items() if info.get(their) is not None}
