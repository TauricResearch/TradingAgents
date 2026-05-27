import json
import sqlite3
import pytest
from datetime import datetime, timezone

from tradingagents.persistence.db import connect
from tradingagents.persistence import store


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture
def conn(tmp_path):
    c = connect(str(tmp_path / "iic.db"))
    store.upsert_watchlist(c, ticker="AAPL", ttl_until=None, tags=["user"])
    return c


def _seed_event(conn, *, ev_id="ev1", ticker="AAPL", salience=0.9, conf=0.9):
    store.insert_event(conn, event_id=ev_id, source="rss",
                       ingested_ts=_now(), salience=salience, raw_path=None,
                       status="triaged", deduped_of=None)
    store.insert_event_ticker(conn, event_id=ev_id, ticker=ticker,
                              confidence=conf)


@pytest.mark.unit
def test_run_once_enqueues_and_suppresses(conn):
    from tradingagents.orchestrator.promoter import run_once
    _seed_event(conn)
    n = run_once(conn, salience_threshold=0.7, ticker_conf_threshold=0.8,
                 batch_size=10, cooldown_min=60)
    assert n == 1
    job = conn.execute("SELECT * FROM queue_jobs").fetchone()
    assert job["job_type"] == "event_alert"
    assert job["trigger_event_id"] == "ev1"
    payload = json.loads(job["payload"])
    assert payload == {"event_id": "ev1", "ticker": "AAPL"}
    sup = conn.execute(
        "SELECT * FROM suppression WHERE key='event_alert:AAPL'"
    ).fetchone()
    assert sup is not None


@pytest.mark.unit
def test_run_once_is_idempotent(conn):
    """Second tick (no new events) enqueues nothing."""
    from tradingagents.orchestrator.promoter import run_once
    _seed_event(conn)
    assert run_once(conn, salience_threshold=0.7, ticker_conf_threshold=0.8,
                    batch_size=10, cooldown_min=60) == 1
    assert run_once(conn, salience_threshold=0.7, ticker_conf_threshold=0.8,
                    batch_size=10, cooldown_min=60) == 0


@pytest.mark.unit
def test_partial_failure_does_not_leave_orphan_suppression(conn, monkeypatch):
    """If upsert_suppression raises mid-tx, the queue_jobs row must roll back."""
    from tradingagents.orchestrator import promoter as p
    _seed_event(conn)

    def boom(*a, **kw):
        raise RuntimeError("simulated db failure")

    monkeypatch.setattr(p.store, "upsert_suppression", boom)
    with pytest.raises(RuntimeError):
        p.run_once(conn, salience_threshold=0.7, ticker_conf_threshold=0.8,
                   batch_size=10, cooldown_min=60)
    # Both writes must be absent — the with-block rolled the tx back.
    assert conn.execute("SELECT COUNT(*) FROM queue_jobs").fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM suppression WHERE key='event_alert:AAPL'"
    ).fetchone()[0] == 0


@pytest.mark.unit
def test_backpressure_disabled_does_not_block(conn):
    from tradingagents.orchestrator.promoter import run_once
    from tradingagents.orchestrator.guards import QueueBackpressure
    _seed_event(conn)
    g = QueueBackpressure(enabled=False, max_pending=0)  # would block if enabled
    assert run_once(conn, salience_threshold=0.7, ticker_conf_threshold=0.8,
                    batch_size=10, cooldown_min=60,
                    backpressure=g) == 1


@pytest.mark.unit
def test_backpressure_enabled_blocks(conn):
    from tradingagents.orchestrator.promoter import run_once
    from tradingagents.orchestrator.guards import QueueBackpressure
    _seed_event(conn)
    g = QueueBackpressure(enabled=True, max_pending=0)
    assert run_once(conn, salience_threshold=0.7, ticker_conf_threshold=0.8,
                    batch_size=10, cooldown_min=60,
                    backpressure=g) == 0
    assert conn.execute("SELECT COUNT(*) FROM queue_jobs").fetchone()[0] == 0
