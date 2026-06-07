"""Application wiring: one runnable alpha cycle.

Composes the pieces into a single entry point:
    ingest -> screen -> trigger/queue -> brain (analyze) -> cost gate -> execute

Dependencies (fetcher, analyzer, broker) are injected so the whole flow is
testable offline; the CLI builds the live ones (yfinance + DeepSeek brain).
"""

from __future__ import annotations

import time
from datetime import date
from typing import Any, Callable, Optional

from .broker import PaperBroker
from .broker.base import Broker
from .broker.commission import CommissionModel
from .ingestion import (
    DEFAULT_MACRO_SERIES,
    ingest_fundamentals,
    ingest_macro,
    ingest_news,
    ingest_price_bars,
    ingest_social,
)
from .ingestion.fundamentals_ingest import FundamentalsFetcher
from .ingestion.macro_ingest import MacroFetcher
from .ingestion.news_ingest import NewsFetcher
from .ingestion.price_ingest import PriceFetcher
from .ingestion.social_ingest import SocialFetcher
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
    news_fetcher: Optional[NewsFetcher] = None,
    fundamentals_fetcher: Optional[FundamentalsFetcher] = None,
    social_fetcher: Optional[SocialFetcher] = None,
) -> None:
    for symbol in symbols:
        ingest_price_bars(session, symbol, fetcher=fetcher, start=start, end=end, interval=interval)
        if news_fetcher is not None:
            ingest_news(session, symbol, fetcher=news_fetcher)
        if fundamentals_fetcher is not None:
            ingest_fundamentals(session, symbol, fetcher=fundamentals_fetcher)
        if social_fetcher is not None:
            ingest_social(session, symbol, fetcher=social_fetcher)
        screen_ticker(session, symbol)


def run_once(
    symbols: list[str],
    *,
    fetcher: PriceFetcher,
    analyzer: Analyzer,
    broker: Optional[Broker] = None,
    commission_model: Optional[CommissionModel] = None,
    news_fetcher: Optional[NewsFetcher] = None,
    fundamentals_fetcher: Optional[FundamentalsFetcher] = None,
    macro_fetcher: Optional[MacroFetcher] = None,
    social_fetcher: Optional[SocialFetcher] = None,
    charter: Optional[dict[str, Any]] = None,
    top_k: Optional[int] = None,
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
        repo.seed_default_charter(s, overrides=charter)  # config Statute
        if macro_fetcher is not None:  # macro is global, ingested once per run
            for sid in DEFAULT_MACRO_SERIES:
                ingest_macro(s, sid, fetcher=macro_fetcher)
        ingest_and_screen(
            s, symbols, fetcher=fetcher, start=start, end=end,
            news_fetcher=news_fetcher, fundamentals_fetcher=fundamentals_fetcher,
            social_fetcher=social_fetcher,
        )

    with database.get_session() as s:
        return run_cycle(
            s, broker, analyzer,
            commission_model=commission_model,
            top_k=top_k or max(1, len(symbols)),
            **sizing,
        )


def run_forever(
    symbols: list[str],
    *,
    interval_seconds: float = 3600.0,
    max_cycles: Optional[int] = None,
    sleep: Callable[[float], None] = time.sleep,
    **run_once_kwargs: Any,
) -> list[CycleReport]:
    """Autonomous loop: the recurring tick is the *periodical synthesis*.

    Each tick refreshes data and runs one cycle. ``max_cycles`` + an injectable
    ``sleep`` make it testable; with the defaults it runs indefinitely. The same
    broker/DB persist across ticks (idempotent ``init_db``).
    """
    reports: list[CycleReport] = []
    n = 0
    while max_cycles is None or n < max_cycles:
        reports.append(run_once(symbols, **run_once_kwargs))
        n += 1
        if max_cycles is not None and n >= max_cycles:
            break
        sleep(interval_seconds)
    return reports
