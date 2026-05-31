import pytest
from tradingagents.persistence.db import connect


@pytest.mark.unit
def test_queue_jobs_has_f4_columns(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    cols = {c[1] for c in conn.execute("PRAGMA table_info(queue_jobs)")}
    assert {"trigger_event_id", "run_ids", "brief_id", "cost_usd", "error"} <= cols


@pytest.mark.unit
def test_briefs_has_trigger_event_id(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    cols = {c[1] for c in conn.execute("PRAGMA table_info(briefs)")}
    assert "trigger_event_id" in cols


@pytest.mark.unit
def test_runs_has_queue_job_id(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    cols = {c[1] for c in conn.execute("PRAGMA table_info(runs)")}
    assert "queue_job_id" in cols


@pytest.mark.unit
def test_idx_queue_jobs_trigger_event_present(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    idx_names = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'"
    )}
    assert "idx_queue_jobs_trigger_event" in idx_names


@pytest.mark.unit
def test_schema_init_is_idempotent(tmp_path):
    """Running connect() twice on the same DB must not raise."""
    db = str(tmp_path / "iic.db")
    conn1 = connect(db)
    conn1.close()
    # Second open re-runs schema.sql; ALTER TABLE ADD COLUMN must be swallowed.
    conn2 = connect(db)
    cols = {c[1] for c in conn2.execute("PRAGMA table_info(queue_jobs)")}
    assert "trigger_event_id" in cols
