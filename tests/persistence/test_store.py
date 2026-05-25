import pytest
import uuid
from datetime import datetime, timezone


@pytest.fixture
def conn(tmp_path):
    from tradingagents.persistence.db import connect
    return connect(str(tmp_path / "test.db"))


@pytest.mark.unit
def test_insert_run_round_trips(conn):
    from tradingagents.persistence import store
    run_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    store.insert_run(conn, run_id=run_id, ticker="AAPL", persona_id="macro",
                     started_ts=now, artifact_dir=f"runs/{run_id}")
    row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    assert row is not None
    assert row["ticker"] == "AAPL"
    assert row["persona_id"] == "macro"
    assert row["status"] == "running"


@pytest.mark.unit
def test_finalize_run_sets_status_and_decision(conn):
    from tradingagents.persistence import store
    run_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    store.insert_run(conn, run_id=run_id, ticker="AAPL", persona_id="macro",
                     started_ts=now, artifact_dir=f"runs/{run_id}")
    store.finalize_run(conn, run_id=run_id, ended_ts=now, status="complete",
                       decision="BUY", confidence=0.72)
    row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    assert row["status"] == "complete"
    assert row["decision"] == "BUY"
    assert row["confidence"] == pytest.approx(0.72)


@pytest.mark.unit
def test_record_cost_appends_row(conn):
    from tradingagents.persistence import store
    run_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    store.insert_run(conn, run_id=run_id, ticker="AAPL", persona_id=None,
                     started_ts=now, artifact_dir=f"runs/{run_id}")
    store.record_cost(conn, run_id=run_id, provider="deepseek",
                      model="deepseek-v4-pro", in_tokens=1000, out_tokens=500)
    rows = list(conn.execute("SELECT * FROM costs WHERE run_id = ?", (run_id,)))
    assert len(rows) == 1
    assert rows[0]["in_tokens"] == 1000
    assert rows[0]["out_tokens"] == 500


@pytest.mark.unit
def test_insert_brief_round_trips(conn):
    from tradingagents.persistence import store
    import uuid
    run_id = uuid.uuid4().hex
    brief_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    store.insert_run(conn, run_id=run_id, ticker="AAPL", persona_id="macro",
                     started_ts=now, artifact_dir=f"runs/{run_id}")
    store.insert_brief(conn, brief_id=brief_id, mode="deep_dive",
                       scope="AAPL", generated_ts=now,
                       content_path=f"briefs/{brief_id}.md",
                       run_ids=[run_id])
    row = conn.execute("SELECT * FROM briefs WHERE brief_id = ?", (brief_id,)).fetchone()
    assert row["mode"] == "deep_dive"
    assert row["scope"] == "AAPL"
    import json as _json
    assert _json.loads(row["run_ids"]) == [run_id]


@pytest.mark.unit
def test_insert_brief_action_round_trips(conn):
    from tradingagents.persistence import store
    import uuid
    run_id = uuid.uuid4().hex
    brief_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    store.insert_run(conn, run_id=run_id, ticker="AAPL", persona_id=None,
                     started_ts=now, artifact_dir=f"runs/{run_id}")
    store.insert_brief(conn, brief_id=brief_id, mode="deep_dive", scope="AAPL",
                       generated_ts=now, content_path="briefs/x.md",
                       run_ids=[run_id])
    expires = "2099-01-01T00:00:00+00:00"
    store.insert_brief_action(conn, brief_id=brief_id,
                              action_type="refine_brief",
                              action_params={"instruction": "more aggressive"},
                              expires_at=expires)
    row = conn.execute("SELECT * FROM brief_actions WHERE brief_id = ?",
                       (brief_id,)).fetchone()
    assert row["action_type"] == "refine_brief"
    assert row["state"] == "pending"
    import json as _json
    assert _json.loads(row["action_params"])["instruction"] == "more aggressive"
