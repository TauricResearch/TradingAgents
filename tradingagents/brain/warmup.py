"""Warm start: pre-run the extractors on a new (empty) analysis.

When the team starts a fresh analysis the ticker may have no data yet — that
emptiness is the trigger. We run the extractors *once*, without waiting for an
agent to call them, so the agents' first injected context is already populated.
During the analysis the agents still call tools autonomously for more/fresh data
(see ``brain/tooling.py``); this only seeds the starting context.

Fill-if-missing: each family is fetched only when nothing is stored yet, so
repeated analyses don't re-pull (and historical data is never re-downloaded).
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from ..ingestion import (
    DEFAULT_MACRO_SERIES,
    ingest_fundamentals,
    ingest_macro,
    ingest_news,
    ingest_price_bars,
    ingest_social,
)
from ..storage import repository as repo
from .tooling import Extractors


def warm_start(session: Session, symbol: str, extractors: Extractors) -> dict[str, bool]:
    """Seed the DB for ``symbol`` from the extractors where data is missing.

    Returns which families were warm-started (useful for logging/tests).
    """
    ex = extractors
    done: dict[str, bool] = {}

    if ex.price_fetcher is not None and repo.latest_price(session, symbol) is None:
        ingest_price_bars(session, symbol, fetcher=ex.price_fetcher,
                          start=ex.history_start, end=date.today().isoformat())
        done["prices"] = True

    if ex.news_fetcher is not None and not repo.recent_news(session, symbol, limit=1):
        ingest_news(session, symbol, fetcher=ex.news_fetcher)
        done["news"] = True

    if ex.fundamentals_fetcher is not None and repo.latest_fundamentals(session, symbol) is None:
        ingest_fundamentals(session, symbol, fetcher=ex.fundamentals_fetcher)
        done["fundamentals"] = True

    if ex.social_fetcher is not None and not repo.recent_social(session, symbol, limit=1):
        ingest_social(session, symbol, fetcher=ex.social_fetcher)
        done["social"] = True

    if ex.macro_fetcher is not None and repo.latest_macro(session, DEFAULT_MACRO_SERIES[0]) is None:
        for sid in DEFAULT_MACRO_SERIES:
            ingest_macro(session, sid, fetcher=ex.macro_fetcher)
        done["macro"] = True

    return done
