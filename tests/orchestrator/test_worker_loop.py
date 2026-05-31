import json
import threading
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


@pytest.mark.unit
def test_main_loop_processes_one_job_on_pool_thread(tmp_path, monkeypatch):
    """End-to-end guard for the S-4 cross-thread fix: worker.main() runs the
    drain on a pool thread that must build its OWN sqlite connection. A
    main-thread connection used on the pool thread raises
    sqlite3.ProgrammingError, which the loop's broad except would swallow,
    leaving the job unprocessed and wedging the worker forever. If that
    regression returns, compose_event_alert never fires, _shutdown is never
    set, and the join() below times out → t.is_alive() asserts False."""
    from tradingagents.orchestrator import worker as worker_mod

    db = str(tmp_path / "iic.db")
    conn = connect(db)
    store.insert_event(conn, event_id="ev1", source="rss", ingested_ts=_now(),
                       salience=0.9, raw_path=None, status="triaged",
                       deduped_of=None)
    store.insert_brief(conn, brief_id="b1", mode="event_alert", scope="AAPL",
                       generated_ts=_now(), content_path="briefs/b1.md",
                       run_ids=[], parent_brief_id=None, trigger_event_id="ev1")
    queue_store.insert_queue_job(conn, job_type="event_alert",
                                 payload=json.dumps({"event_id": "ev1",
                                                     "ticker": "AAPL"}),
                                 trigger_event_id="ev1")
    conn.close()

    sec = MagicMock()

    def _compose(**kwargs):
        worker_mod._shutdown = True   # stop the loop after this one job
        return "b1"

    sec.compose_event_alert.side_effect = _compose
    # _build_secretary would need real LLM creds; substitute the mock. It is
    # invoked on the pool thread inside _drain_once, exactly where the conn is
    # also created — proving thread-affinity is satisfied.
    monkeypatch.setattr(worker_mod, "_build_secretary", lambda cfg, c: sec)
    # signal.signal() only works on the main thread; main() runs in a thread here.
    monkeypatch.setattr(worker_mod, "_install_signal_handlers", lambda: None)

    cfg = {"iic_db_path": db, "worker_poll_interval_s": 0,
           "worker_job_timeout_min": 1, "daily_budget_enabled": False}

    worker_mod._shutdown = False
    t = threading.Thread(target=worker_mod.main, kwargs={"config": cfg},
                         daemon=True)
    t.start()
    t.join(timeout=15)
    worker_mod._shutdown = False   # reset module global for other tests

    assert not t.is_alive(), ("worker.main did not exit — likely a cross-thread "
                              "sqlite ProgrammingError wedged the loop")
    verify = connect(db)
    row = verify.execute("SELECT state, brief_id FROM queue_jobs "
                         "WHERE trigger_event_id='ev1'").fetchone()
    assert row["state"] == "done"
    assert row["brief_id"] == "b1"
