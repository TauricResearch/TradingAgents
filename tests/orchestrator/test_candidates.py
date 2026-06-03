import pytest
from datetime import datetime, timezone, timedelta

from tradingagents.persistence.db import connect
from tradingagents.persistence import store


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture
def conn(tmp_path):
    c = connect(str(tmp_path / "iic.db"))
    # Watchlist contains AAPL
    store.upsert_watchlist(c, ticker="AAPL", ttl_until=None, tags=["user"])
    return c


def _seed_event(conn, *, ev_id, ticker, salience, confidence, status="triaged"):
    store.insert_event(conn, event_id=ev_id, source="rss",
                       ingested_ts=_now(), salience=salience, raw_path=None,
                       status=status, deduped_of=None)
    store.insert_event_ticker(conn, event_id=ev_id, ticker=ticker,
                              confidence=confidence)


@pytest.mark.unit
def test_high_salience_watchlist_event_is_candidate(conn):
    from tradingagents.orchestrator.candidates import fetch_candidates
    _seed_event(conn, ev_id="ev1", ticker="AAPL", salience=0.9, confidence=0.9)
    rows = fetch_candidates(conn, salience_threshold=0.7,
                            ticker_conf_threshold=0.8, limit=50)
    assert len(rows) == 1
    assert rows[0]["event_id"] == "ev1"
    assert rows[0]["ticker"] == "AAPL"


@pytest.mark.unit
def test_low_salience_event_is_skipped(conn):
    from tradingagents.orchestrator.candidates import fetch_candidates
    _seed_event(conn, ev_id="ev1", ticker="AAPL", salience=0.5, confidence=0.9)
    rows = fetch_candidates(conn, salience_threshold=0.7,
                            ticker_conf_threshold=0.8, limit=50)
    assert rows == []


@pytest.mark.unit
def test_low_confidence_ticker_is_skipped(conn):
    from tradingagents.orchestrator.candidates import fetch_candidates
    _seed_event(conn, ev_id="ev1", ticker="AAPL", salience=0.9, confidence=0.6)
    assert fetch_candidates(conn, salience_threshold=0.7,
                            ticker_conf_threshold=0.8, limit=50) == []


@pytest.mark.unit
def test_off_watchlist_ticker_is_skipped(conn):
    from tradingagents.orchestrator.candidates import fetch_candidates
    _seed_event(conn, ev_id="ev1", ticker="TSLA", salience=0.9, confidence=0.9)
    assert fetch_candidates(conn, salience_threshold=0.7,
                            ticker_conf_threshold=0.8, limit=50) == []


@pytest.mark.unit
def test_duplicate_status_event_is_skipped(conn):
    from tradingagents.orchestrator.candidates import fetch_candidates
    _seed_event(conn, ev_id="ev1", ticker="AAPL", salience=0.9,
                confidence=0.9, status="duplicate")
    assert fetch_candidates(conn, salience_threshold=0.7,
                            ticker_conf_threshold=0.8, limit=50) == []


@pytest.mark.unit
def test_suppressed_ticker_is_skipped(conn):
    from tradingagents.orchestrator.candidates import fetch_candidates
    _seed_event(conn, ev_id="ev1", ticker="AAPL", salience=0.9, confidence=0.9)
    until = (datetime.now(timezone.utc) + timedelta(minutes=60)).isoformat()
    store.upsert_suppression(conn, key="event_alert:AAPL", until_ts=until,
                              reason="cooldown", created_by="test")
    assert fetch_candidates(conn, salience_threshold=0.7,
                            ticker_conf_threshold=0.8, limit=50) == []


@pytest.mark.unit
def test_expired_suppression_does_not_skip(conn):
    from tradingagents.orchestrator.candidates import fetch_candidates
    _seed_event(conn, ev_id="ev1", ticker="AAPL", salience=0.9, confidence=0.9)
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    store.upsert_suppression(conn, key="event_alert:AAPL", until_ts=past,
                              reason="cooldown", created_by="test")
    rows = fetch_candidates(conn, salience_threshold=0.7,
                            ticker_conf_threshold=0.8, limit=50)
    assert len(rows) == 1


@pytest.mark.unit
def test_already_enqueued_event_is_skipped(conn):
    """Idempotency guard: an event already referenced by queue_jobs.trigger_event_id
    is never returned again."""
    from tradingagents.orchestrator.candidates import fetch_candidates
    from tradingagents.orchestrator.queue_store import insert_queue_job
    _seed_event(conn, ev_id="ev1", ticker="AAPL", salience=0.9, confidence=0.9)
    insert_queue_job(conn, job_type="event_alert",
                     payload="{}", trigger_event_id="ev1")
    assert fetch_candidates(conn, salience_threshold=0.7,
                            ticker_conf_threshold=0.8, limit=50) == []


@pytest.mark.unit
def test_limit_respected_and_ordered_by_ingested_ts(conn):
    from tradingagents.orchestrator.candidates import fetch_candidates
    base = datetime.now(timezone.utc)
    for i in range(3):
        ts = (base + timedelta(seconds=i)).isoformat()
        conn.execute(
            "INSERT INTO events (event_id, source, ingested_ts, salience, "
            "raw_path, deduped_of, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (f"ev{i}", "rss", ts, 0.9, None, None, "triaged"),
        )
        store.insert_event_ticker(conn, event_id=f"ev{i}", ticker="AAPL",
                                   confidence=0.9)
    conn.commit()
    rows = fetch_candidates(conn, salience_threshold=0.7,
                            ticker_conf_threshold=0.8, limit=2)
    assert [r["event_id"] for r in rows] == ["ev0", "ev1"]


@pytest.mark.unit
def test_fetch_candidates_grouped_by_event(tmp_path):
    from tradingagents.persistence.db import connect
    from tradingagents.persistence import store
    from tradingagents.orchestrator.candidates import fetch_candidates_grouped

    conn = connect(str(tmp_path / "iic.db"))
    store.upsert_watchlist(conn, ticker="NVDA", ttl_until=None, tags=["user"])
    store.upsert_watchlist(conn, ticker="PANW", ttl_until=None, tags=["user"])
    store.insert_event(conn, event_id="ev1", source="rss",
                       ingested_ts="2026-06-01T00:00:00+00:00", salience=0.9,
                       raw_path=None, status="triaged", deduped_of=None)
    store.insert_event_ticker(conn, event_id="ev1", ticker="NVDA", confidence=1.0)
    store.insert_event_ticker(conn, event_id="ev1", ticker="PANW", confidence=1.0)

    groups = fetch_candidates_grouped(conn, salience_threshold=0.85,
                                      ticker_conf_threshold=0.9, limit=50)
    assert len(groups) == 1
    assert groups[0]["event_id"] == "ev1"
    assert sorted(groups[0]["tickers"]) == ["NVDA", "PANW"]
