import pytest

from tradingagents.persistence.db import connect as iic_connect


@pytest.mark.unit
def test_fetch_queue_depth_by_state(tmp_path):
    from tradingagents.dashboard.panels.queue import fetch_queue_depth, fetch_recent_jobs

    conn = iic_connect(str(tmp_path / "iic.db"))
    # Use real schema: job_type, payload, state, enqueued_ts
    conn.executemany(
        "INSERT INTO queue_jobs (job_type, payload, state, enqueued_ts) "
        "VALUES ('event_alert', '{}', ?, ?)",
        [("queued", "2026-05-27T10:00:00+00:00"),
         ("queued", "2026-05-27T10:01:00+00:00"),
         ("done",    "2026-05-27T09:00:00+00:00"),
         ("running", "2026-05-27T09:30:00+00:00")],
    )
    conn.commit()

    depth = fetch_queue_depth(conn)
    assert depth.get("queued") == 2
    assert depth.get("done") == 1
    assert depth.get("running") == 1

    jobs = fetch_recent_jobs(conn, limit=10)
    assert len(jobs) == 4
