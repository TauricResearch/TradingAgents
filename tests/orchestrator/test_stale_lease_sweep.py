import pytest
from datetime import datetime, timezone

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
