"""Tests for social ingestion and its use in the Sentiment context."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tradingagents.brain.context import sentiment_context
from tradingagents.ingestion import ingest_social
from tradingagents.storage import database, init_db, reset_engine
from tradingagents.storage import repository as repo

pytestmark = pytest.mark.unit


@pytest.fixture()
def db(tmp_path):
    init_db(f"sqlite:///{tmp_path / 'social.db'}")
    yield
    reset_engine()


class FakeSocial:
    def __init__(self, items):
        self._items = items

    def fetch(self, symbol):
        return list(self._items)


def _items():
    base = datetime(2026, 6, 1, tzinfo=timezone.utc)
    return [
        {"id": 1, "ts": base, "platform": "stocktwits", "body": "AAPL to the moon", "sentiment": 1.0},
        {"id": 2, "ts": base + timedelta(hours=1), "platform": "stocktwits", "body": "AAPL overvalued", "sentiment": -1.0},
    ]


def test_ingest_social_and_dedup(db):
    fetcher = FakeSocial(_items())
    with database.get_session() as s:
        r1 = ingest_social(s, "AAPL", fetcher=fetcher)
        assert r1.inserted == 2 and r1.skipped == 0
    with database.get_session() as s:
        r2 = ingest_social(s, "AAPL", fetcher=fetcher)  # same ids -> deduped
        assert r2.inserted == 0 and r2.skipped == 2
    with database.get_session() as s:
        assert len(repo.recent_social(s, "AAPL")) == 2


def test_sentiment_context_includes_social(db):
    with database.get_session() as s:
        ingest_social(s, "AAPL", fetcher=FakeSocial(_items()))
    with database.get_session() as s:
        ctx = sentiment_context(s, "AAPL")
        assert "to the moon" in ctx and "stocktwits" in ctx


def test_sentiment_context_social_placeholder(db):
    with database.get_session() as s:
        assert "(no social posts in DB)" in sentiment_context(s, "AAPL")
