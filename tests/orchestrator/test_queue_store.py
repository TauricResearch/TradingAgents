import json
import pytest
from datetime import datetime, timezone

from tradingagents.persistence.db import connect
from tradingagents.persistence import store


@pytest.fixture
def conn(tmp_path):
    c = connect(str(tmp_path / "iic.db"))
    store.insert_event(c, event_id="ev1", source="rss",
                       ingested_ts=datetime.now(timezone.utc).isoformat(),
                       salience=0.9, raw_path=None,
                       status="triaged", deduped_of=None)
    return c


@pytest.mark.unit
def test_insert_queue_job_returns_id(conn):
    from tradingagents.orchestrator.queue_store import insert_queue_job
    job_id = insert_queue_job(
        conn, job_type="event_alert",
        payload=json.dumps({"event_id": "ev1", "ticker": "AAPL"}),
        trigger_event_id="ev1",
    )
    row = conn.execute("SELECT * FROM queue_jobs WHERE job_id = ?", (job_id,)).fetchone()
    assert row["state"] == "queued"
    assert row["trigger_event_id"] == "ev1"


@pytest.mark.unit
def test_lease_one_returns_none_on_empty(conn):
    from tradingagents.orchestrator.queue_store import lease_one
    assert lease_one(conn) is None


@pytest.mark.unit
def test_lease_one_flips_state(conn):
    from tradingagents.orchestrator.queue_store import insert_queue_job, lease_one
    job_id = insert_queue_job(conn, job_type="event_alert",
                              payload="{}", trigger_event_id="ev1")
    leased = lease_one(conn)
    assert leased["job_id"] == job_id
    assert leased["state"] == "running"
    row = conn.execute("SELECT * FROM queue_jobs WHERE job_id=?", (job_id,)).fetchone()
    assert row["state"] == "running"
    assert row["started_ts"] is not None


@pytest.mark.unit
def test_mark_done_records_outputs(conn):
    from tradingagents.orchestrator.queue_store import (
        insert_queue_job, lease_one, mark_done,
    )
    insert_queue_job(conn, job_type="event_alert",
                     payload="{}", trigger_event_id="ev1")
    job = lease_one(conn)
    mark_done(conn, job_id=job["job_id"], run_ids=["r1", "r2"],
              brief_id=None, cost_usd=0.45)
    row = conn.execute("SELECT * FROM queue_jobs WHERE job_id=?", (job["job_id"],)).fetchone()
    assert row["state"] == "done"
    # brief_id may be None (FK enforcement); we pass None here to avoid the FK
    assert row["cost_usd"] == pytest.approx(0.45)
    assert json.loads(row["run_ids"]) == ["r1", "r2"]
    assert row["finished_ts"] is not None


@pytest.mark.unit
def test_mark_error_records_exception_message(conn):
    from tradingagents.orchestrator.queue_store import (
        insert_queue_job, lease_one, mark_error,
    )
    insert_queue_job(conn, job_type="event_alert",
                     payload="{}", trigger_event_id="ev1")
    job = lease_one(conn)
    mark_error(conn, job_id=job["job_id"], error_msg="LLM upstream timeout")
    row = conn.execute("SELECT * FROM queue_jobs WHERE job_id=?", (job["job_id"],)).fetchone()
    assert row["state"] == "error"
    assert row["error"] == "LLM upstream timeout"


@pytest.mark.unit
def test_pending_count(conn):
    from tradingagents.orchestrator.queue_store import (
        insert_queue_job, lease_one, pending_count,
    )
    insert_queue_job(conn, job_type="event_alert", payload="{}", trigger_event_id="ev1")
    insert_queue_job(conn, job_type="event_alert", payload="{}", trigger_event_id="ev1")
    assert pending_count(conn) == 2
    lease_one(conn)
    assert pending_count(conn) == 2  # leased ('running') still counts as pending


@pytest.mark.unit
def test_daily_enqueue_count(conn):
    from tradingagents.orchestrator.queue_store import insert_queue_job, daily_enqueue_count
    insert_queue_job(conn, job_type="event_alert", payload="{}", trigger_event_id="ev1")
    insert_queue_job(conn, job_type="event_alert", payload="{}", trigger_event_id="ev1")
    assert daily_enqueue_count(conn) == 2


@pytest.mark.unit
def test_daily_cost_total_sums_done_jobs(conn):
    from tradingagents.orchestrator.queue_store import (
        insert_queue_job, lease_one, mark_done, daily_cost_total,
    )
    for _ in range(3):
        insert_queue_job(conn, job_type="event_alert", payload="{}", trigger_event_id="ev1")
        job = lease_one(conn)
        mark_done(conn, job_id=job["job_id"], run_ids=[], brief_id=None, cost_usd=1.25)
    assert daily_cost_total(conn) == pytest.approx(3.75)


@pytest.mark.unit
def test_sweep_stale_leases_marks_old_running_as_error(conn):
    from tradingagents.orchestrator.queue_store import (
        insert_queue_job, lease_one, sweep_stale_leases,
    )
    insert_queue_job(conn, job_type="event_alert", payload="{}", trigger_event_id="ev1")
    job = lease_one(conn)
    # Manually backdate started_ts to 2h ago.
    conn.execute(
        "UPDATE queue_jobs SET started_ts = datetime('now', '-2 hour') "
        "WHERE job_id = ?", (job["job_id"],),
    )
    conn.commit()
    n = sweep_stale_leases(conn, max_age_seconds=3600)
    assert n == 1
    row = conn.execute("SELECT * FROM queue_jobs WHERE job_id=?", (job["job_id"],)).fetchone()
    assert row["state"] == "error"
    assert "stale_lease" in row["error"]
