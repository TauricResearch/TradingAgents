"""Application wiring: one runnable alpha cycle.

Composes the pieces into a single entry point:
    ingest -> screen -> trigger/queue -> brain (analyze) -> cost gate -> execute

Dependencies (fetcher, analyzer, broker) are injected so the whole flow is
testable offline; the CLI builds the live ones (yfinance + DeepSeek brain).
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from .broker import PaperBroker
from .broker.base import Broker
from .broker.commission import CommissionModel
from .ingestion import ingest_price_bars
from .ingestion.price_ingest import PriceFetcher
from .ingestion.screening import screen_ticker
from .orchestration import CycleReport, run_cycle
from .orchestration.analyze import Analyzer
from .storage import database, init_db
from .storage import repository as repo


def ensure_initial_portfolio(session, cash: float = 100_000.0) -> None:
    """Seed a starting portfolio snapshot if none exists (sizing needs it)."""
    if repo.latest_portfolio_snapshot(session) is None:
        repo.save_portfolio_snapshot(session, cash=cash, total_value=cash, positions=[])


def ingest_and_screen(
    session,
    symbols: list[str],
    *,
    fetcher: PriceFetcher,
    start: str,
    end: str,
    interval: str = "1d",
) -> None:
    for symbol in symbols:
        ingest_price_bars(session, symbol, fetcher=fetcher, start=start, end=end, interval=interval)
        screen_ticker(session, symbol)


def run_once(
    symbols: list[str],
    *,
    fetcher: PriceFetcher,
    analyzer: Analyzer,
    broker: Optional[Broker] = None,
    commission_model: Optional[CommissionModel] = None,
    db_url: Optional[str] = None,
    start: str = "2024-01-01",
    end: Optional[str] = None,
    **sizing: Any,
) -> CycleReport:
    """Run a single end-to-end cycle and return the report."""
    init_db(db_url)
    broker = broker or PaperBroker()
    end = end or date.today().isoformat()

    with database.get_session() as s:
        ensure_initial_portfolio(s)
        repo.seed_default_charter(s)
        ingest_and_screen(s, symbols, fetcher=fetcher, start=start, end=end)

    with database.get_session() as s:
        return run_cycle(
            s, broker, analyzer,
            commission_model=commission_model,
            top_k=max(1, len(symbols)),
            **sizing,
        )
