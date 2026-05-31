import pytest
from datetime import datetime, timedelta, timezone

from tradingagents.persistence.db import connect
from tradingagents.persistence import store
from tradingagents.orchestrator import queue_store


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture
def db(tmp_path, monkeypatch):
    p = str(tmp_path / "iic.db")
    monkeypatch.setenv("TRADINGAGENTS_IIC_DB_PATH", p)
    return p


def _seed_brief_with_latency(conn, *, latency_seconds, ev_id, brief_id):
    base = datetime.now(timezone.utc) - timedelta(minutes=30)
    ev_ts = base.isoformat()
    brief_ts = (base + timedelta(seconds=latency_seconds)).isoformat()
    store.insert_event(conn, event_id=ev_id, source="rss",
                       ingested_ts=ev_ts, salience=0.9, raw_path=None,
                       status="triaged", deduped_of=None)
    store.insert_brief(conn, brief_id=brief_id, mode="event_alert",
                       scope="AAPL", generated_ts=brief_ts,
                       content_path=f"briefs/{brief_id}.md",
                       run_ids=["r"], parent_brief_id=None,
                       trigger_event_id=ev_id)


@pytest.mark.unit
def test_evaluator_computes_latency_percentiles(db):
    from scripts.f4_exit_gate import evaluate
    conn = connect(db)
    for i, sec in enumerate([60, 180, 600, 800, 900]):
        _seed_brief_with_latency(conn, latency_seconds=sec,
                                  ev_id=f"ev{i}", brief_id=f"b{i}")
    since = datetime.now(timezone.utc) - timedelta(hours=1)
    result = evaluate(conn, since=since, window_hours=2)
    assert result["brief_count"] == 5
    # p95 of [60, 180, 600, 800, 900] ≈ 900s
    assert result["latency_p95_s"] >= 800
    assert result["latency_p95_s"] <= 900


@pytest.mark.unit
def test_evaluator_passes_when_p95_under_15min(db):
    from scripts.f4_exit_gate import evaluate
    conn = connect(db)
    for i, sec in enumerate([60, 120, 180, 240, 300]):
        _seed_brief_with_latency(conn, latency_seconds=sec,
                                  ev_id=f"ev{i}", brief_id=f"b{i}")
    since = datetime.now(timezone.utc) - timedelta(hours=1)
    result = evaluate(conn, since=since, window_hours=2)
    assert result["sla_pass"] is True
    assert result["sla_rule_applied"] == "p95"


@pytest.mark.unit
def test_evaluator_uses_max_rule_when_one_or_two_briefs(db):
    from scripts.f4_exit_gate import evaluate
    conn = connect(db)
    _seed_brief_with_latency(conn, latency_seconds=500,
                              ev_id="ev0", brief_id="b0")
    since = datetime.now(timezone.utc) - timedelta(hours=1)
    result = evaluate(conn, since=since, window_hours=2)
    assert result["brief_count"] == 1
    assert result["sla_rule_applied"] == "max"
    assert result["sla_pass"] is True   # 500s < 15min


@pytest.mark.unit
def test_evaluator_marks_zero_briefs_as_inconclusive(db):
    from scripts.f4_exit_gate import evaluate
    conn = connect(db)
    since = datetime.now(timezone.utc) - timedelta(hours=1)
    result = evaluate(conn, since=since, window_hours=2)
    assert result["brief_count"] == 0
    assert result["sla_pass"] is None   # inconclusive
    assert result["sla_rule_applied"] == "none"
