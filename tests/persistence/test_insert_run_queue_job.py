import pytest
from datetime import datetime, timezone

from tradingagents.persistence.db import connect
from tradingagents.persistence import store


@pytest.mark.unit
def test_insert_run_with_queue_job_id(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    # Seed a queue_jobs row first so the FK resolves.
    cur = conn.execute(
        "INSERT INTO queue_jobs (job_type, payload, state, enqueued_ts) "
        "VALUES ('event_alert', '{}', 'running', ?)",
        (datetime.now(timezone.utc).isoformat(),),
    )
    job_id = cur.lastrowid
    conn.commit()

    store.insert_run(
        conn,
        run_id="r1", ticker="AAPL", persona_id="macro",
        started_ts=datetime.now(timezone.utc).isoformat(),
        artifact_dir="runs/r1",
        trigger_id=None,
        queue_job_id=job_id,
    )
    row = conn.execute("SELECT * FROM runs WHERE run_id='r1'").fetchone()
    assert row["queue_job_id"] == job_id


@pytest.mark.unit
def test_insert_run_queue_job_id_defaults_none(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    store.insert_run(
        conn,
        run_id="r1", ticker="AAPL", persona_id=None,
        started_ts=datetime.now(timezone.utc).isoformat(),
        artifact_dir="runs/r1",
    )
    row = conn.execute("SELECT * FROM runs WHERE run_id='r1'").fetchone()
    assert row["queue_job_id"] is None
