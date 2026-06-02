import json
from unittest.mock import MagicMock
import pytest

from tradingagents.persistence.db import connect
from tradingagents.persistence import store


def _seed_event(conn):
    store.insert_event(conn, event_id="ev1", source="rss",
                       ingested_ts="2026-06-01T00:00:00+00:00", salience=0.9,
                       raw_path=None, status="triaged", deduped_of=None)


@pytest.mark.unit
def test_compose_light_creates_brief_actions_and_suppression(tmp_path):
    from tradingagents.secretary.service import Secretary
    conn = connect(str(tmp_path / "iic.db"))
    _seed_event(conn)
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content="Short summary of the event.")
    sec = Secretary(conn=conn, data_dir=str(tmp_path / "data"), llm=llm)

    brief_id = sec.compose_event_alert_light(
        event_id="ev1", tickers=["NVDA", "PANW"], ttl_hours=24,
        deliver=False,
    )

    brief = store.get_brief(conn, brief_id=brief_id)
    assert brief["mode"] == "event_alert_light"
    assert sorted(json.loads(brief["scope"])) == ["NVDA", "PANW"]
    assert json.loads(brief["run_ids"]) == []
    assert brief["trigger_event_id"] == "ev1"

    actions = store.fetch_pending_run_full_study(conn)
    assert sorted(json.loads(a["action_params"])["ticker"] for a in actions) == ["NVDA", "PANW"]

    for t in ("NVDA", "PANW"):
        sup = conn.execute("SELECT * FROM suppression WHERE key=?",
                           (f"event_alert:{t}",)).fetchone()
        assert sup is not None
    # exactly one quick LLM call (the summary)
    assert llm.invoke.call_count == 1
