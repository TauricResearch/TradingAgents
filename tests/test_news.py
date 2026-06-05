"""Tests for news ingestion (DB-first dedup) and its use in the brain context."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tradingagents.brain.context import market_context, sentiment_context
from tradingagents.ingestion import ingest_news
from tradingagents.storage import database, init_db, reset_engine
from tradingagents.storage import repository as repo

pytestmark = pytest.mark.unit


@pytest.fixture()
def db(tmp_path):
    init_db(f"sqlite:///{tmp_path / 'news.db'}")
    yield
    reset_engine()


class FakeNews:
    def __init__(self, items):
        self._items = items

    def fetch(self, symbol):
        return list(self._items)


def _items():
    base = datetime(2026, 6, 1, tzinfo=timezone.utc)
    return [
        {"ts": base, "headline": "AAPL beats earnings", "url": "u1", "source": "Reuters"},
        {"ts": base + timedelta(days=1), "headline": "AAPL new product", "url": "u2", "source": "WSJ"},
    ]


def test_ingest_news_and_dedup(db):
    fetcher = FakeNews(_items())
    with database.get_session() as s:
        r1 = ingest_news(s, "AAPL", fetcher=fetcher)
        assert r1.inserted == 2 and r1.skipped == 0
    with database.get_session() as s:
        r2 = ingest_news(s, "AAPL", fetcher=fetcher)  # same urls -> deduped
        assert r2.inserted == 0 and r2.skipped == 2
    with database.get_session() as s:
        assert len(repo.recent_news(s, "AAPL")) == 2


def test_context_includes_news(db):
    with database.get_session() as s:
        ingest_news(s, "AAPL", fetcher=FakeNews(_items()))
    with database.get_session() as s:
        assert "AAPL beats earnings" in market_context(s, "AAPL")
        assert "AAPL new product" in sentiment_context(s, "AAPL")


def test_context_no_news_placeholder(db):
    with database.get_session() as s:
        assert "(no news in DB)" in sentiment_context(s, "AAPL")
