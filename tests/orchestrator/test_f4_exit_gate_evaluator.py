import pytest
from datetime import datetime, timedelta, timezone

from tradingagents.persistence.db import connect
from tradingagents.persistence import store
from scripts.f4_exit_gate import evaluate


def _iso(dt):
    return dt.isoformat()


@pytest.mark.unit
def test_alert_latency_pass(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    base = datetime(2026, 6, 1, tzinfo=timezone.utc)
    # event ingested at base; light brief 1 min later → within 5-min SLA
    store.insert_event(conn, event_id="ev1", source="rss", ingested_ts=_iso(base),
                       salience=0.9, raw_path=None, status="triaged", deduped_of=None)
    store.insert_brief(conn, brief_id="lb1", mode="event_alert_light",
                       scope='["NVDA"]', generated_ts=_iso(base + timedelta(minutes=1)),
                       content_path="briefs/lb1.md", run_ids=[], trigger_event_id="ev1")
    res = evaluate(conn, since=base - timedelta(minutes=1), window_hours=1)
    assert res["alert_count"] == 1
    assert res["sla_pass"] is True
    assert res["alert_latency_p95_s"] <= 5 * 60


@pytest.mark.unit
def test_alert_latency_fail(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    base = datetime(2026, 6, 1, tzinfo=timezone.utc)
    store.insert_event(conn, event_id="ev1", source="rss", ingested_ts=_iso(base),
                       salience=0.9, raw_path=None, status="triaged", deduped_of=None)
    store.insert_brief(conn, brief_id="lb1", mode="event_alert_light",
                       scope='["NVDA"]', generated_ts=_iso(base + timedelta(minutes=12)),
                       content_path="briefs/lb1.md", run_ids=[], trigger_event_id="ev1")
    res = evaluate(conn, since=base - timedelta(minutes=1), window_hours=1)
    assert res["sla_pass"] is False


@pytest.mark.unit
def test_alert_latency_inconclusive_when_no_alerts(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    base = datetime(2026, 6, 1, tzinfo=timezone.utc)
    res = evaluate(conn, since=base, window_hours=1)
    assert res["alert_count"] == 0
    assert res["sla_pass"] is None


@pytest.mark.unit
def test_approved_full_briefs_counted(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    base = datetime(2026, 6, 1, tzinfo=timezone.utc)
    store.insert_event(conn, event_id="ev1", source="rss", ingested_ts=_iso(base),
                       salience=0.9, raw_path=None, status="triaged", deduped_of=None)
    store.insert_brief(conn, brief_id="lb1", mode="event_alert_light",
                       scope='["NVDA"]', generated_ts=_iso(base + timedelta(minutes=1)),
                       content_path="briefs/lb1.md", run_ids=[], trigger_event_id="ev1")
    # a full brief produced from the light alert (parent_brief_id set)
    store.insert_brief(conn, brief_id="fb1", mode="event_alert", scope="NVDA",
                       generated_ts=_iso(base + timedelta(minutes=20)),
                       content_path="briefs/fb1.md", run_ids=["r1"],
                       parent_brief_id="lb1", trigger_event_id="ev1")
    res = evaluate(conn, since=base - timedelta(minutes=1), window_hours=1)
    assert res["approved_full_briefs"] == 1
