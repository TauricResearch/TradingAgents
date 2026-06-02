import pytest
from tradingagents.persistence.db import connect
from tradingagents.persistence import store


def _seed_light_brief(conn, brief_id="lb1"):
    # Create the event first (FK constraint)
    store.insert_event(conn, event_id="ev1", source="polygon_news",
                       ingested_ts="2026-06-01T00:00:00+00:00", salience=0.9,
                       raw_path=None, status="triaged", deduped_of=None)
    store.insert_brief(
        conn, brief_id=brief_id, mode="event_alert_light",
        scope='["NVDA", "PANW"]', generated_ts="2026-06-01T00:00:00+00:00",
        content_path=f"briefs/{brief_id}.md", run_ids=[],
        trigger_event_id="ev1",
    )


@pytest.mark.unit
def test_fetch_pending_run_full_study_actions(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    _seed_light_brief(conn)
    store.insert_brief_action(conn, brief_id="lb1", action_type="run_full_study",
                              action_params={"ticker": "NVDA"},
                              expires_at="2099-01-01T00:00:00+00:00")
    store.insert_brief_action(conn, brief_id="lb1", action_type="run_full_study",
                              action_params={"ticker": "PANW"},
                              expires_at="2099-01-01T00:00:00+00:00")
    rows = store.fetch_pending_run_full_study(conn)
    assert len(rows) == 2
    tickers = sorted(__import__("json").loads(r["action_params"])["ticker"] for r in rows)
    assert tickers == ["NVDA", "PANW"]


@pytest.mark.unit
def test_fetch_pending_run_full_study_excludes_non_pending(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    _seed_light_brief(conn)
    aid = store.insert_brief_action(conn, brief_id="lb1",
                                    action_type="run_full_study",
                                    action_params={"ticker": "NVDA"},
                                    expires_at="2099-01-01T00:00:00+00:00")
    store.update_action_state(conn, action_id=aid, state="accepted",
                              responded_at="2026-06-01T01:00:00+00:00")
    assert store.fetch_pending_run_full_study(conn) == []
