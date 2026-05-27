import json
import pytest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import MagicMock

from tradingagents.persistence.db import connect
from tradingagents.persistence import store


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture
def setup(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    raw = tmp_path / "data" / "events" / "ev1.json"
    raw.parent.mkdir(parents=True)
    raw.write_text(json.dumps({"text": "trigger event text"}))
    store.insert_event(conn, event_id="ev1", source="rss",
                       ingested_ts=_now(), salience=0.9,
                       raw_path=str(raw),
                       status="triaged", deduped_of=None)
    return conn, str(tmp_path / "data")


@pytest.mark.unit
def test_dispatch_event_alert_calls_secretary_with_payload(setup):
    from tradingagents.orchestrator.dispatch import dispatch_event_alert

    conn, data_dir = setup
    sec = MagicMock()
    sec.compose_event_alert.return_value = "b1"

    # Seed brief row so the dispatch_event_alert post-call lookup finds run_ids
    store.insert_brief(conn, brief_id="b1", mode="event_alert",
                       scope="AAPL", generated_ts=_now(),
                       content_path="briefs/b1.md",
                       run_ids=[], parent_brief_id=None,
                       trigger_event_id="ev1")

    job = {
        "job_id": 1,
        "job_type": "event_alert",
        "payload": json.dumps({"event_id": "ev1", "ticker": "AAPL"}),
        "trigger_event_id": "ev1",
    }
    result = dispatch_event_alert(conn, job, secretary=sec)

    sec.compose_event_alert.assert_called_once_with(
        event_id="ev1", ticker="AAPL", job_id=1
    )
    assert result["brief_id"] == "b1"
    assert result["run_ids"] == []
    assert result["cost_usd"] == 0.0


@pytest.mark.unit
def test_dispatch_event_alert_cost_rollup(setup):
    from tradingagents.orchestrator.dispatch import dispatch_event_alert

    conn, data_dir = setup
    sec = MagicMock()
    sec.compose_event_alert.return_value = "b1"

    # Seed a queue_jobs row so runs.queue_job_id FK resolves.
    cur = conn.execute(
        "INSERT INTO queue_jobs (job_type, payload, state, enqueued_ts) "
        "VALUES ('event_alert', '{}', 'running', ?)",
        (_now(),),
    )
    job_id = cur.lastrowid
    conn.commit()

    # Seed two run rows + two costs rows with known dollar values
    for rid in ("r1", "r2"):
        store.insert_run(conn, run_id=rid, ticker="AAPL", persona_id="macro",
                         started_ts=_now(), artifact_dir=f"runs/{rid}",
                         queue_job_id=job_id)
        store.finalize_run(conn, run_id=rid, ended_ts=_now(),
                            status="complete", decision="BUY", confidence=None)
        store.record_cost(conn, run_id=rid, provider="deepseek",
                          model="m", in_tokens=100, out_tokens=50,
                          usd_estimate=0.25)
    # Also seed a brief row with run_ids so dispatch can find them
    store.insert_brief(conn, brief_id="b1", mode="event_alert",
                       scope="AAPL", generated_ts=_now(),
                       content_path="briefs/b1.md",
                       run_ids=["r1", "r2"], parent_brief_id=None,
                       trigger_event_id="ev1")

    job = {
        "job_id": job_id,
        "job_type": "event_alert",
        "payload": json.dumps({"event_id": "ev1", "ticker": "AAPL"}),
        "trigger_event_id": "ev1",
    }
    result = dispatch_event_alert(conn, job, secretary=sec)
    assert result["cost_usd"] == pytest.approx(0.50)
    assert sorted(result["run_ids"]) == ["r1", "r2"]


@pytest.mark.unit
def test_dispatch_unknown_job_type_raises(setup):
    from tradingagents.orchestrator.dispatch import dispatch

    conn, data_dir = setup
    sec = MagicMock()
    job = {"job_id": 1, "job_type": "morning_digest", "payload": "{}",
           "trigger_event_id": None}
    with pytest.raises(ValueError, match="unknown job_type"):
        dispatch(conn, job, secretary=sec)
