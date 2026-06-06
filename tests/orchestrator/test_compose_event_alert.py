import json
import pytest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import MagicMock

from tradingagents.persistence.db import connect
from tradingagents.persistence import store
from tradingagents.secretary.service import Secretary


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture
def setup(tmp_path):
    """Seed events row, raw payload on disk, three completed runs."""
    db = str(tmp_path / "iic.db")
    data_dir = tmp_path / "data"
    (data_dir / "events").mkdir(parents=True, exist_ok=True)
    raw_path = data_dir / "events" / "ev1.json"
    raw_path.write_text(json.dumps({
        "text": "Apple beats Q3 earnings by 12%.",
        "source": "polygon_news",
    }))

    conn = connect(db)
    # Seed a queue_jobs row so FK from runs.queue_job_id resolves.
    cur = conn.execute(
        "INSERT INTO queue_jobs (job_type, payload, state, enqueued_ts) "
        "VALUES ('event_alert', '{}', 'running', ?)",
        (_now(),),
    )
    job_id = cur.lastrowid
    conn.commit()

    store.insert_event(conn, event_id="ev1", source="polygon_news",
                       ingested_ts=_now(), salience=0.9,
                       raw_path=str(raw_path),
                       status="triaged", deduped_of=None)
    # Three mock completed runs
    for rid, pid, dec in [("r1", "macro", "HOLD"),
                          ("r2", "value", "BUY"),
                          ("r3", "momentum", "BUY")]:
        artifact_dir = f"runs/{rid}"
        (data_dir / artifact_dir).mkdir(parents=True)
        (data_dir / artifact_dir / "pm_synthesis.md").write_text(
            f"## {pid}\n\nDecision: **{dec}**\nReason: ...\n"
        )
        store.insert_run(conn, run_id=rid, ticker="AAPL",
                         persona_id=pid, started_ts=_now(),
                         artifact_dir=artifact_dir, queue_job_id=job_id)
        store.finalize_run(conn, run_id=rid, ended_ts=_now(),
                            status="complete", decision=dec, confidence=None)
    return conn, str(data_dir), job_id


@pytest.mark.unit
def test_compose_event_alert_writes_brief(setup, monkeypatch):
    """Given pre-seeded runs, compose_event_alert produces a brief row,
    a markdown file, and a synthesis that includes the trigger event."""
    conn, data_dir, job_id = setup

    # Mock the analysis runner so this test doesn't actually invoke the graph.
    def fake_runner(*, ticker, trade_date, config, event_context, queue_job_id):
        return ["r1", "r2", "r3"]
    monkeypatch.setattr(
        "tradingagents.secretary.service.run_default_analysis",
        fake_runner,
    )

    # Mock synthesize_brief to return a known structure.
    def fake_synth(*, llm, ticker, persona_runs, event_context=None):
        assert event_context == "Apple beats Q3 earnings by 12%."
        return {
            "consensus": "Beat is real.",
            "divergence": "Macro neutral; value+momentum BUY.",
            "recommendation": "BUY (high confidence)",
        }
    monkeypatch.setattr(
        "tradingagents.secretary.service.synthesize_brief",
        fake_synth,
    )

    sec = Secretary(conn=conn, data_dir=data_dir, llm=MagicMock())
    brief_id = sec.compose_event_alert(event_id="ev1", ticker="AAPL", job_id=job_id)

    # briefs row exists, trigger_event_id linked
    b = store.get_brief(conn, brief_id=brief_id)
    assert b["mode"] == "event_alert"
    assert b["trigger_event_id"] == "ev1"
    assert b["scope"] == "AAPL"
    assert b["analysis_pack_id"] is not None

    # markdown file written; contains the trigger event text
    md_path = Path(data_dir) / "briefs" / f"{brief_id}.md"
    assert md_path.exists()
    content = md_path.read_text()
    assert "Apple beats Q3 earnings by 12%." in content
    assert "BUY (high confidence)" in content

    pack = conn.execute(
        "SELECT * FROM analysis_packs WHERE pack_id = ?",
        (b["analysis_pack_id"],),
    ).fetchone()
    assert pack is not None
    pack_body = json.loads((Path(data_dir) / pack["content_path"]).read_text())
    assert pack_body["event_id"] == "ev1"
    assert pack_body["ticker"] == "AAPL"
    assert pack_body["event_context"] == "Apple beats Q3 earnings by 12%."


@pytest.mark.unit
def test_compose_event_alert_returns_brief_id_string(setup, monkeypatch):
    conn, data_dir, job_id = setup
    monkeypatch.setattr(
        "tradingagents.secretary.service.run_default_analysis",
        lambda **kw: ["r1", "r2", "r3"],
    )
    monkeypatch.setattr(
        "tradingagents.secretary.service.synthesize_brief",
        lambda **kw: {"consensus": "x", "divergence": "y", "recommendation": "z"},
    )
    sec = Secretary(conn=conn, data_dir=data_dir, llm=MagicMock())
    brief_id = sec.compose_event_alert(event_id="ev1", ticker="AAPL", job_id=job_id)
    assert isinstance(brief_id, str)
    assert len(brief_id) == 32   # uuid4 hex
