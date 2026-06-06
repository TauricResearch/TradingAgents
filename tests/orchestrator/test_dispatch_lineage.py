import json
from unittest.mock import MagicMock

from tradingagents.persistence.db import connect
from tradingagents.persistence import store
from tradingagents.orchestrator.dispatch import dispatch_event_alert


def test_dispatch_uses_payload_parent_brief_and_marks_action_done(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    store.insert_event(
        conn,
        event_id="ev1",
        source="rss",
        ingested_ts="2026-06-01T00:00:00+00:00",
        salience=0.9,
        raw_path=None,
        status="triaged",
        deduped_of=None,
    )
    store.insert_brief(
        conn,
        brief_id="light1",
        mode="event_alert_light",
        scope='["NVDA"]',
        generated_ts="2026-06-01T00:00:00+00:00",
        content_path="briefs/light1.md",
        run_ids=[],
        trigger_event_id="ev1",
    )
    aid = store.insert_brief_action(
        conn,
        brief_id="light1",
        action_type="run_full_study",
        action_params={"ticker": "NVDA"},
        expires_at="2026-06-02T00:00:00+00:00",
    )
    secretary = MagicMock()
    secretary.compose_event_alert.return_value = "full1"
    store.insert_brief(
        conn,
        brief_id="full1",
        mode="event_alert",
        scope="NVDA",
        generated_ts="2026-06-01T00:05:00+00:00",
        content_path="briefs/full1.md",
        run_ids=["r1"],
        parent_brief_id="light1",
        trigger_event_id="ev1",
    )

    result = dispatch_event_alert(
        conn,
        {
            "job_id": 42,
            "payload": json.dumps(
                {
                    "event_id": "ev1",
                    "ticker": "NVDA",
                    "action_id": aid,
                    "parent_brief_id": "light1",
                }
            ),
        },
        secretary=secretary,
    )

    assert result["brief_id"] == "full1"
    secretary.compose_event_alert.assert_called_once_with(
        event_id="ev1",
        ticker="NVDA",
        job_id=42,
        parent_brief_id="light1",
    )
    row = conn.execute(
        "SELECT result_brief_id FROM brief_actions WHERE action_id = ?",
        (aid,),
    ).fetchone()
    assert row["result_brief_id"] == "full1"
