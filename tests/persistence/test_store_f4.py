import pytest
from datetime import datetime, timezone, timedelta

from tradingagents.persistence.db import connect
from tradingagents.persistence import store


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@pytest.mark.unit
def test_insert_brief_threads_trigger_event_id(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    store.insert_event(conn, event_id="ev1", source="polygon_news",
                       ingested_ts=_now(), salience=0.9, raw_path=None,
                       status="triaged", deduped_of=None)
    store.insert_brief(
        conn, brief_id="b1", mode="event_alert", scope="AAPL",
        generated_ts=_now(), content_path="briefs/b1.md",
        run_ids=["r1"], parent_brief_id=None, trigger_event_id="ev1",
    )
    row = conn.execute(
        "SELECT trigger_event_id FROM briefs WHERE brief_id='b1'"
    ).fetchone()
    assert row["trigger_event_id"] == "ev1"


@pytest.mark.unit
def test_insert_brief_default_trigger_event_id_none(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    store.insert_brief(
        conn, brief_id="b2", mode="deep_dive", scope="AAPL",
        generated_ts=_now(), content_path="briefs/b2.md",
        run_ids=["r1"], parent_brief_id=None,
    )
    row = conn.execute(
        "SELECT trigger_event_id FROM briefs WHERE brief_id='b2'"
    ).fetchone()
    assert row["trigger_event_id"] is None


@pytest.mark.unit
def test_get_event_returns_dict_with_text_path(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    store.insert_event(conn, event_id="ev1", source="rss",
                       ingested_ts=_now(), salience=0.8,
                       raw_path="data/events/ev1.json",
                       status="triaged", deduped_of=None)
    ev = store.get_event(conn, event_id="ev1")
    assert ev["event_id"] == "ev1"
    assert ev["raw_path"] == "data/events/ev1.json"
    assert ev["salience"] == pytest.approx(0.8)


@pytest.mark.unit
def test_get_event_missing_returns_none(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    assert store.get_event(conn, event_id="missing") is None


@pytest.mark.unit
def test_upsert_suppression_inserts_then_updates(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    until = (datetime.now(timezone.utc) + timedelta(minutes=60)).isoformat()
    store.upsert_suppression(
        conn, key="event_alert:AAPL", until_ts=until,
        reason="alert_cooldown event_id=ev1", created_by="promoter",
    )
    row = conn.execute(
        "SELECT * FROM suppression WHERE key='event_alert:AAPL'"
    ).fetchone()
    assert row["until_ts"] == until

    # second call extends the cooldown
    new_until = (datetime.now(timezone.utc) + timedelta(minutes=120)).isoformat()
    store.upsert_suppression(
        conn, key="event_alert:AAPL", until_ts=new_until,
        reason="alert_cooldown event_id=ev2", created_by="promoter",
    )
    row2 = conn.execute(
        "SELECT * FROM suppression WHERE key='event_alert:AAPL'"
    ).fetchone()
    assert row2["until_ts"] == new_until
    assert row2["reason"] == "alert_cooldown event_id=ev2"


@pytest.mark.unit
def test_get_brief_round_trip(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    # Seed the referenced event first (FK is enforced).
    store.insert_event(conn, event_id="ev1", source="rss",
                       ingested_ts=_now(), salience=0.9, raw_path=None,
                       status="triaged", deduped_of=None)
    store.insert_brief(
        conn, brief_id="b1", mode="event_alert", scope="AAPL",
        generated_ts=_now(), content_path="briefs/b1.md",
        run_ids=["r1", "r2"], parent_brief_id=None,
        trigger_event_id="ev1",
    )
    b = store.get_brief(conn, brief_id="b1")
    assert b["mode"] == "event_alert"
    assert b["trigger_event_id"] == "ev1"
