import json
import pytest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import MagicMock

from tradingagents.persistence.db import connect
from tradingagents.persistence import store
from tradingagents.orchestrator import queue_store


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture
def setup(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    raw = tmp_path / "data" / "events" / "ev1.json"
    raw.parent.mkdir(parents=True)
    raw.write_text(json.dumps({"text": "ev text"}))
    store.insert_event(conn, event_id="ev1", source="rss",
                       ingested_ts=_now(), salience=0.9, raw_path=str(raw),
                       status="triaged", deduped_of=None)
    return conn, str(tmp_path / "data")


@pytest.mark.unit
def test_drain_one_processes_a_queued_job(setup):
    from tradingagents.orchestrator.worker import drain_one
    conn, data_dir = setup
    sec = MagicMock()
    sec.compose_event_alert.return_value = "b1"
    # Seed brief so dispatch_event_alert's lookup finds it.
    store.insert_brief(conn, brief_id="b1", mode="event_alert",
                       scope="AAPL", generated_ts=_now(),
                       content_path="briefs/b1.md",
                       run_ids=[], parent_brief_id=None,
                       trigger_event_id="ev1")
    queue_store.insert_queue_job(conn, job_type="event_alert",
                                  payload=json.dumps({"event_id": "ev1",
                                                       "ticker": "AAPL"}),
                                  trigger_event_id="ev1")
    result = drain_one(conn, secretary=sec)
    assert result is True
    row = conn.execute(
        "SELECT * FROM queue_jobs WHERE trigger_event_id='ev1'"
    ).fetchone()
    assert row["state"] == "done"
    assert row["brief_id"] == "b1"
    assert row["finished_ts"] is not None


@pytest.mark.unit
def test_drain_one_returns_false_when_queue_empty(setup):
    from tradingagents.orchestrator.worker import drain_one
    conn, data_dir = setup
    sec = MagicMock()
    assert drain_one(conn, secretary=sec) is False


@pytest.mark.unit
def test_drain_one_marks_error_on_failure(setup):
    from tradingagents.orchestrator.worker import drain_one
    conn, data_dir = setup
    sec = MagicMock()
    sec.compose_event_alert.side_effect = RuntimeError("LLM died")
    queue_store.insert_queue_job(conn, job_type="event_alert",
                                  payload=json.dumps({"event_id": "ev1",
                                                       "ticker": "AAPL"}),
                                  trigger_event_id="ev1")
    drain_one(conn, secretary=sec)
    row = conn.execute(
        "SELECT * FROM queue_jobs WHERE trigger_event_id='ev1'"
    ).fetchone()
    assert row["state"] == "error"
    assert "LLM died" in row["error"]


@pytest.mark.unit
def test_drain_one_skipped_when_budget_blocks(setup):
    """When DailyBudgetGuard.gate() returns False, the job is not leased."""
    from tradingagents.orchestrator.worker import drain_one
    from tradingagents.orchestrator.guards import DailyBudgetGuard
    conn, data_dir = setup
    sec = MagicMock()
    # Pre-spend $1 of "today" first so it owns the lowest job_id and gets
    # leased+marked done before the AAPL event_alert job we want to gate.
    queue_store.insert_queue_job(conn, job_type="event_alert",
                                  payload="{}", trigger_event_id="ev1")
    sentinel = queue_store.lease_one(conn)
    queue_store.mark_done(conn, job_id=sentinel["job_id"], run_ids=[],
                          brief_id=None, cost_usd=1.0)
    # Now insert the AAPL job that the guard should keep in 'queued'.
    queue_store.insert_queue_job(conn, job_type="event_alert",
                                  payload=json.dumps({"event_id": "ev1",
                                                       "ticker": "AAPL"}),
                                  trigger_event_id="ev1")
    blocker = DailyBudgetGuard(enabled=True, daily_usd=0.5)
    result = drain_one(conn, secretary=sec, budget_guard=blocker)
    assert result is False
    # Original event-alert job is still 'queued' (not leased)
    row = conn.execute(
        "SELECT state FROM queue_jobs WHERE trigger_event_id='ev1' AND "
        "payload LIKE '%AAPL%'"
    ).fetchone()
    assert row["state"] == "queued"
