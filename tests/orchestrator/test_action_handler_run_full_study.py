import json
from unittest.mock import MagicMock
import pytest

from tradingagents.persistence.db import connect
from tradingagents.persistence import store


def _seed_light(conn, brief_id="lb1"):
    store.insert_event(conn, event_id="ev1", source="rss",
                       ingested_ts="2026-06-01T00:00:00+00:00", salience=0.9,
                       raw_path=None, status="triaged", deduped_of=None)
    store.insert_brief(conn, brief_id=brief_id, mode="event_alert_light",
                       scope='["NVDA"]', generated_ts="2026-06-01T00:00:00+00:00",
                       content_path=f"briefs/{brief_id}.md", run_ids=[],
                       trigger_event_id="ev1")


@pytest.mark.unit
def test_accepted_run_full_study_enqueues_event_alert_job(tmp_path):
    from tradingagents.orchestrator.action_handler import tick
    conn = connect(str(tmp_path / "iic.db"))
    _seed_light(conn)
    aid = store.insert_brief_action(conn, brief_id="lb1",
                                    action_type="run_full_study",
                                    action_params={"ticker": "NVDA"},
                                    expires_at="2099-01-01T00:00:00+00:00")
    store.update_action_state(conn, action_id=aid, state="accepted",
                              responded_at="2026-06-01T01:00:00+00:00")

    tick(conn=conn, secretary=MagicMock(), dispatch_backtest=MagicMock())

    job = conn.execute("SELECT job_type, payload, trigger_event_id "
                       "FROM queue_jobs").fetchone()
    assert job["job_type"] == "event_alert"
    assert json.loads(job["payload"]) == {"event_id": "ev1", "ticker": "NVDA"}
    assert job["trigger_event_id"] == "ev1"
    # action marked done (result_brief_id set) so it won't re-dispatch
    row = conn.execute("SELECT result_brief_id FROM brief_actions "
                       "WHERE action_id=?", (aid,)).fetchone()
    assert row[0] is not None


@pytest.mark.unit
def test_run_full_study_is_idempotent(tmp_path):
    from tradingagents.orchestrator.action_handler import tick
    conn = connect(str(tmp_path / "iic.db"))
    _seed_light(conn)
    aid = store.insert_brief_action(conn, brief_id="lb1",
                                    action_type="run_full_study",
                                    action_params={"ticker": "NVDA"},
                                    expires_at="2099-01-01T00:00:00+00:00")
    store.update_action_state(conn, action_id=aid, state="accepted",
                              responded_at="2026-06-01T01:00:00+00:00")
    tick(conn=conn, secretary=MagicMock(), dispatch_backtest=MagicMock())
    tick(conn=conn, secretary=MagicMock(), dispatch_backtest=MagicMock())
    assert conn.execute("SELECT COUNT(*) FROM queue_jobs").fetchone()[0] == 1


@pytest.mark.unit
def test_run_full_study_missing_ticker_does_not_enqueue_or_mark_done(tmp_path):
    from tradingagents.orchestrator.action_handler import tick
    conn = connect(str(tmp_path / "iic.db"))
    _seed_light(conn)
    # action_params with no "ticker" key
    aid = store.insert_brief_action(conn, brief_id="lb1",
                                    action_type="run_full_study",
                                    action_params={},
                                    expires_at="2099-01-01T00:00:00+00:00")
    store.update_action_state(conn, action_id=aid, state="accepted",
                              responded_at="2026-06-01T01:00:00+00:00")
    tick(conn=conn, secretary=MagicMock(), dispatch_backtest=MagicMock())
    # no job enqueued, action NOT marked done (still recoverable)
    assert conn.execute("SELECT COUNT(*) FROM queue_jobs").fetchone()[0] == 0
    row = conn.execute("SELECT result_brief_id FROM brief_actions "
                       "WHERE action_id=?", (aid,)).fetchone()
    assert row[0] is None
