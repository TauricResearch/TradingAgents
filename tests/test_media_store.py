"""Media store: dedup, stats, look-ahead-safe windowing, and URL routing.

Exercises the default stdlib SQLite backend (no extra deps). The SQLAlchemy
backend shares the same interface and dedup semantics; it's covered indirectly
by the routing test and exercised live against a real DB.
"""
from datetime import datetime, timezone

import pytest

from tradingagents.dataflows.media_store import (
    SqlAlchemyMediaStore,
    SqliteMediaStore,
    _history_bounds,
    _normalize_pg_url,
    _window_bounds,
    open_store,
)


def _epoch(s: str) -> float:
    return datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).timestamp()


def _row(source, ext_id, ticker, created, **kw):
    base = {"source": source, "external_id": ext_id, "ticker": ticker,
            "subreddit": None, "author": None, "sentiment": None,
            "created_utc": created, "title": None, "body": "", "fetched_utc": 0.0}
    base.update(kw)
    return base


@pytest.fixture
def store(tmp_path):
    s = SqliteMediaStore(tmp_path / "media.db")
    yield s
    s.close()


@pytest.mark.unit
def test_store_dedups_on_source_and_external_id(store):
    rows = [_row("stocktwits", "1", "NVDA", _epoch("2026-06-20 10:00")),
            _row("stocktwits", "2", "NVDA", _epoch("2026-06-20 11:00"))]
    assert store.store(rows) == 2          # both new
    assert store.store(rows) == 0          # same ids → no new inserts
    # Same external_id under a different source is a distinct row.
    assert store.store([_row("reddit", "1", "NVDA", _epoch("2026-06-20 12:00"))]) == 1


@pytest.mark.unit
def test_store_empty_is_noop(store):
    assert store.store([]) == 0


@pytest.mark.unit
def test_stats_groups_by_ticker_and_source(store):
    store.store([
        _row("news", "a", "NVDA", _epoch("2026-06-18 09:00")),
        _row("news", "b", "NVDA", _epoch("2026-06-20 09:00")),
        _row("reddit", "c", "MU", _epoch("2026-06-19 09:00")),
    ])
    stats = {(t, s): (n, lo, hi) for t, s, n, lo, hi in store.stats()}
    assert stats[("NVDA", "news")][0] == 2
    assert stats[("NVDA", "news")][1] == _epoch("2026-06-18 09:00")  # min
    assert stats[("NVDA", "news")][2] == _epoch("2026-06-20 09:00")  # max
    assert stats[("MU", "reddit")][0] == 1


@pytest.mark.unit
def test_window_is_lookahead_safe(store):
    # end=2026-06-28 cuts off at midnight UTC, so a post at 20:58 that day is
    # OUTSIDE the window (a decision made on the 28th can't see the 28th's later
    # intraday chatter); a post within the prior 7 days is inside.
    store.store([
        _row("reddit", "in", "NVDA", _epoch("2026-06-24 09:00")),
        _row("reddit", "edge_before", "NVDA", _epoch("2026-06-28 00:00")),  # == midnight, included
        _row("stocktwits", "same_day_intraday", "NVDA", _epoch("2026-06-28 20:58")),
        _row("reddit", "too_old", "NVDA", _epoch("2026-06-10 09:00")),
    ])
    ids = {r["external_id"] for r in store.window("nvda", "2026-06-28", days=7)}
    assert ids == {"in", "edge_before"}


@pytest.mark.unit
def test_window_bounds_midnight_cutoff():
    lo, hi = _window_bounds("2026-06-28", 7)
    assert hi == _epoch("2026-06-28 00:00")
    assert lo == _epoch("2026-06-21 00:00")


@pytest.mark.unit
def test_history_asof_requires_both_publish_and_fetch_before_cutoff(store):
    store.store([
        _row("news", "known", "NVDA", _epoch("2026-06-28 12:00"),
             fetched_utc=_epoch("2026-06-28 13:00")),
        _row("news", "late_discovery", "NVDA", _epoch("2026-06-27 12:00"),
             fetched_utc=_epoch("2026-06-29 01:00")),
        _row("news", "future_post", "NVDA", _epoch("2026-06-29 01:00"),
             fetched_utc=_epoch("2026-06-28 13:00")),
        _row("stocktwits", "wrong_source", "NVDA", _epoch("2026-06-28 14:00"),
             fetched_utc=_epoch("2026-06-28 14:01")),
    ])

    rows = store.history_asof(
        "2026-06-21", "2026-06-28", tickers=["nvda"], sources=["news"]
    )

    assert [row["external_id"] for row in rows] == ["known"]


@pytest.mark.unit
def test_history_asof_supports_pseudo_ticker_prefixes(store):
    store.store([
        _row("trendnews", "trend", "@TREND_WORLD", _epoch("2026-06-28 12:00"),
             fetched_utc=_epoch("2026-06-28 13:00")),
        _row("news", "ticker", "NVDA", _epoch("2026-06-28 12:00"),
             fetched_utc=_epoch("2026-06-28 13:00")),
    ])
    rows = store.history_asof(
        "2026-06-21", "2026-06-28", ticker_prefixes=["@trend"], limit=10
    )
    assert [row["external_id"] for row in rows] == ["trend"]


@pytest.mark.unit
def test_history_bounds_include_full_decision_session():
    lo, hi = _history_bounds("2026-06-21", "2026-06-28")
    assert lo == _epoch("2026-06-21 00:00")
    assert hi == _epoch("2026-06-29 00:00")


def _odds(market_id, captured, prob, theme="rates", volume=1000.0):
    return {"theme": theme, "topic": "Fed rate cut", "market_id": market_id,
            "captured_utc": captured, "question": f"q{market_id}",
            "probability": prob, "volume": volume, "resolution_utc": None}


@pytest.mark.unit
def test_store_odds_is_a_time_series_keyed_by_capture(store):
    # Same market re-captured at different times → distinct snapshots.
    assert store.store_odds([_odds("m1", _epoch("2026-06-20 10:00"), 0.40)]) == 1
    assert store.store_odds([_odds("m1", _epoch("2026-06-21 10:00"), 0.55)]) == 1
    # Re-inserting an existing (market_id, captured_utc) is a no-op.
    assert store.store_odds([_odds("m1", _epoch("2026-06-21 10:00"), 0.55)]) == 0


@pytest.mark.unit
def test_odds_asof_returns_latest_snapshot_before_cutoff(store):
    store.store_odds([
        _odds("m1", _epoch("2026-06-20 10:00"), 0.40),
        _odds("m1", _epoch("2026-06-25 10:00"), 0.60),   # latest before 06-28
        _odds("m1", _epoch("2026-06-28 09:00"), 0.90),   # same-day → excluded (midnight cutoff)
        _odds("m2", _epoch("2026-06-24 10:00"), 0.30, theme="trade"),
    ])
    asof = {r["market_id"]: r["probability"] for r in store.odds_asof("2026-06-28")}
    assert asof == {"m1": 0.60, "m2": 0.30}        # newest pre-cutoff per market
    # Theme filter narrows the set.
    only_rates = store.odds_asof("2026-06-28", themes=["rates"])
    assert {r["market_id"] for r in only_rates} == {"m1"}


@pytest.mark.unit
def test_normalize_pg_url_forces_psycopg_driver():
    # Fly Managed Postgres / Heroku give postgres://; plain postgresql:// would
    # default to psycopg2. Both must become postgresql+psycopg://.
    assert _normalize_pg_url("postgres://u:p@h:5432/db") == "postgresql+psycopg://u:p@h:5432/db"
    assert _normalize_pg_url("postgresql://u:p@h:5432/db") == "postgresql+psycopg://u:p@h:5432/db"
    # Already-qualified and non-Postgres URLs pass through untouched.
    assert _normalize_pg_url("postgresql+psycopg://u@h/db") == "postgresql+psycopg://u@h/db"
    assert _normalize_pg_url("sqlite:///x.db") == "sqlite:///x.db"


@pytest.mark.unit
def test_open_store_routing(tmp_path):
    # Bare path and sqlite:/// URLs both resolve to the stdlib SQLite backend.
    s1 = open_store(str(tmp_path / "bare.db"))
    s2 = open_store(f"sqlite:///{tmp_path / 'scheme.db'}")
    try:
        assert isinstance(s1, SqliteMediaStore)
        assert isinstance(s2, SqliteMediaStore)
    finally:
        s1.close()
        s2.close()


@pytest.mark.unit
def test_sqlalchemy_store_reports_insert_count_with_conflict_ignore(tmp_path):
    store = SqlAlchemyMediaStore(f"sqlite+pysqlite:///{tmp_path / 'sa.db'}")
    rows = [
        _row("news", "1", "NVDA", _epoch("2026-07-23 10:00")),
        _row("news", "2", "NVDA", _epoch("2026-07-23 11:00")),
    ]
    try:
        assert store.store(rows) == 2
        assert store.store(rows) == 0
    finally:
        store.close()
