import pytest
from datetime import datetime, timezone, timedelta

from tradingagents.persistence.db import connect
from tradingagents.persistence import store
from tradingagents.orchestrator import queue_store


@pytest.mark.unit
def test_worker_sweeps_stale_leases_on_boot(tmp_path):
    """A run-loop iteration that starts with a stale 'running' job marks
    it as 'error' and then proceeds normally."""
    from tradingagents.orchestrator.worker import boot_sweep
    db = str(tmp_path / "iic.db")
    conn = connect(db)
    store.insert_event(conn, event_id="ev1", source="rss",
                       ingested_ts=datetime.now(timezone.utc).isoformat(),
                       salience=0.9, raw_path=None,
                       status="triaged", deduped_of=None)
    queue_store.insert_queue_job(conn, job_type="event_alert",
                                  payload="{}", trigger_event_id="ev1")
    job = queue_store.lease_one(conn)
    conn.execute(
        "UPDATE queue_jobs SET started_ts = datetime('now', '-2 hour') "
        "WHERE job_id = ?", (job["job_id"],),
    )
    conn.commit()

    n = boot_sweep(conn, max_age_seconds=3600)
    assert n == 1
    row = conn.execute("SELECT state FROM queue_jobs WHERE job_id=?",
                        (job["job_id"],)).fetchone()
    assert row["state"] == "error"


@pytest.mark.unit
def test_sweep_reclaims_same_day_iso_t_started_ts(tmp_path):
    """Regression (S-4): lease_one writes started_ts via datetime.isoformat()
    ('T' separator + '+00:00' offset). The sweep must wrap the column in
    datetime() before comparing to datetime('now', ?); a raw string compare
    silently never reclaims a job that went stale earlier *today* ('T' 0x54 >
    ' ' 0x20), which would make the worker's stale-lease recovery a no-op."""
    db = str(tmp_path / "iic.db")
    conn = connect(db)
    store.insert_event(conn, event_id="ev1", source="rss",
                       ingested_ts=datetime.now(timezone.utc).isoformat(),
                       salience=0.9, raw_path=None,
                       status="triaged", deduped_of=None)
    queue_store.insert_queue_job(conn, job_type="event_alert",
                                  payload="{}", trigger_event_id="ev1")
    job = queue_store.lease_one(conn)
    # Same calendar day, 2h ago, in the EXACT ISO-8601 'T'+offset form lease_one
    # uses — not SQLite's space form. This is what masks the bug in practice.
    stale = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    assert "T" in stale and stale.endswith("+00:00")
    conn.execute("UPDATE queue_jobs SET started_ts = ? WHERE job_id = ?",
                 (stale, job["job_id"]))
    conn.commit()

    n = queue_store.sweep_stale_leases(conn, max_age_seconds=3600,
                                       reason="stale_lease_swept_in_loop")
    assert n == 1
    row = conn.execute("SELECT state, error FROM queue_jobs WHERE job_id=?",
                        (job["job_id"],)).fetchone()
    assert row["state"] == "error"
    assert row["error"] == "stale_lease_swept_in_loop"
