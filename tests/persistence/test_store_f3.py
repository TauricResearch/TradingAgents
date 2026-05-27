import json
import pytest
from datetime import datetime, timezone, timedelta

from tradingagents.persistence.db import connect


@pytest.fixture
def conn(tmp_path):
    return connect(str(tmp_path / "iic.db"))


@pytest.mark.unit
def test_insert_event(conn):
    from tradingagents.persistence.store import insert_event
    insert_event(
        conn, event_id="e1", source="polygon_news",
        ingested_ts=datetime.now(timezone.utc).isoformat(),
        salience=0.9, raw_path="data/events/e1.json",
        status="triaged", deduped_of=None,
    )
    row = conn.execute("SELECT * FROM events WHERE event_id='e1'").fetchone()
    assert row["status"] == "triaged"
    assert row["salience"] == pytest.approx(0.9)


@pytest.mark.unit
def test_insert_event_ticker(conn):
    from tradingagents.persistence.store import insert_event, insert_event_ticker
    insert_event(conn, event_id="e1", source="rss",
                 ingested_ts=datetime.now(timezone.utc).isoformat(),
                 salience=0.6, raw_path="data/events/e1.json",
                 status="triaged", deduped_of=None)
    insert_event_ticker(conn, event_id="e1", ticker="AAPL", confidence=0.92)
    row = conn.execute("SELECT * FROM event_ticker WHERE event_id='e1'").fetchone()
    assert row["ticker"] == "AAPL"
    assert row["confidence"] == pytest.approx(0.92)


@pytest.mark.unit
def test_upsert_watchlist_user(conn):
    from tradingagents.persistence.store import upsert_watchlist
    upsert_watchlist(conn, ticker="AAPL", ttl_until=None, tags=["user"])
    row = conn.execute("SELECT * FROM watchlist WHERE ticker='AAPL'").fetchone()
    assert row["ttl_until"] is None
    assert "user" in json.loads(row["tags"])


@pytest.mark.unit
def test_upsert_watchlist_auto(conn):
    from tradingagents.persistence.store import upsert_watchlist
    ttl = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    upsert_watchlist(conn, ticker="TSLA", ttl_until=ttl,
                     tags=["auto", "event:e-42"])
    row = conn.execute("SELECT * FROM watchlist WHERE ticker='TSLA'").fetchone()
    assert row["ttl_until"] == ttl
    assert set(json.loads(row["tags"])) == {"auto", "event:e-42"}


@pytest.mark.unit
def test_upsert_watchlist_preserves_added_ts(conn):
    """Second upsert must NOT overwrite the original added_ts."""
    from tradingagents.persistence.store import upsert_watchlist
    upsert_watchlist(conn, ticker="NVDA", ttl_until=None, tags=["user"])
    first = conn.execute("SELECT added_ts FROM watchlist WHERE ticker='NVDA'").fetchone()
    upsert_watchlist(conn, ticker="NVDA", ttl_until=None, tags=["user", "extra"])
    second = conn.execute("SELECT added_ts FROM watchlist WHERE ticker='NVDA'").fetchone()
    assert first["added_ts"] == second["added_ts"]


@pytest.mark.unit
def test_get_active_watchlist(conn):
    from tradingagents.persistence.store import upsert_watchlist, get_active_watchlist
    now = datetime.now(timezone.utc)
    upsert_watchlist(conn, ticker="AAPL", ttl_until=None, tags=["user"])
    upsert_watchlist(conn, ticker="OLD",
                     ttl_until=(now - timedelta(days=1)).isoformat(),
                     tags=["auto"])
    upsert_watchlist(conn, ticker="TSLA",
                     ttl_until=(now + timedelta(days=3)).isoformat(),
                     tags=["auto"])
    active = get_active_watchlist(conn)
    assert set(active) == {"AAPL", "TSLA"}  # OLD is expired


@pytest.mark.unit
def test_upsert_ticker_and_get_set(conn):
    from tradingagents.persistence.store import upsert_ticker, get_tickers_set
    upsert_ticker(conn, ticker="AAPL", exchange="NASDAQ",
                  name="Apple Inc.", aliases=["Apple"], active=True)
    upsert_ticker(conn, ticker="DEAD", exchange="NYSE",
                  name="Defunct Co", aliases=[], active=False)
    s = get_tickers_set(conn)
    assert "AAPL" in s
    assert "DEAD" not in s  # inactive filtered out


@pytest.mark.unit
def test_insert_event_fingerprint(conn):
    from tradingagents.persistence.store import insert_event, insert_event_fingerprint
    insert_event(conn, event_id="e1", source="rss",
                 ingested_ts=datetime.now(timezone.utc).isoformat(),
                 salience=0.5, raw_path="data/events/e1.json",
                 status="triaged", deduped_of=None)
    insert_event_fingerprint(conn, fingerprint="abc123",
                             kind="sha256", event_id="e1", source="rss")
    row = conn.execute(
        "SELECT * FROM event_fingerprints WHERE fingerprint='abc123' AND kind='sha256'"
    ).fetchone()
    assert row["event_id"] == "e1"


@pytest.mark.unit
def test_insert_event_embedding(conn):
    from tradingagents.persistence.store import insert_event, insert_event_embedding
    insert_event(conn, event_id="e1", source="rss",
                 ingested_ts=datetime.now(timezone.utc).isoformat(),
                 salience=0.5, raw_path="data/events/e1.json",
                 status="triaged", deduped_of=None)
    insert_event_embedding(conn, event_id="e1", vec_id=42)
    row = conn.execute("SELECT * FROM event_embeddings WHERE event_id='e1'").fetchone()
    assert row["vec_id"] == 42
