import json
import time
import pytest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import MagicMock

from tradingagents.persistence.db import connect
from tradingagents.persistence import store
from tradingagents.orchestrator import queue_store, promoter, worker


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@pytest.mark.smoke
def test_f4_synthetic_event_produces_brief_under_60s(tmp_path, monkeypatch):
    """End-to-end: inject a salient triaged event, run promoter once,
    run drain_one once, assert a brief lands.

    Bypasses the real graph by mocking `Secretary.compose_event_alert`."""
    db = str(tmp_path / "iic.db")
    data_dir = str(tmp_path / "data")
    monkeypatch.setenv("TRADINGAGENTS_IIC_DB_PATH", db)
    monkeypatch.setenv("TRADINGAGENTS_IIC_DATA_DIR", data_dir)

    # Reload config so the env vars take effect.
    import importlib
    import tradingagents.default_config as m
    importlib.reload(m)

    # Seed: watchlist + raw event file + events row
    conn = connect(db)
    store.upsert_watchlist(conn, ticker="AAPL", ttl_until=None, tags=["user"])
    (Path(data_dir) / "events").mkdir(parents=True, exist_ok=True)
    raw = Path(data_dir) / "events" / "ev1.json"
    raw.write_text(json.dumps({"text": "Apple beats Q3 earnings by 12%.",
                               "source": "polygon_news"}))
    store.insert_event(conn, event_id="ev1", source="polygon_news",
                       ingested_ts=_now(), salience=0.9,
                       raw_path=str(raw),
                       status="triaged", deduped_of=None)
    store.insert_event_ticker(conn, event_id="ev1", ticker="AAPL",
                              confidence=0.95)

    # Promoter: one cycle
    n = promoter.run_once(conn,
                          salience_threshold=0.7,
                          ticker_conf_threshold=0.8,
                          batch_size=10, cooldown_min=60)
    assert n == 1, "promoter should have enqueued one job"
    assert queue_store.pending_count(conn) == 1

    # Worker: mock secretary to avoid real LLM/graph
    sec = MagicMock()

    def fake_compose(event_id, ticker, job_id):
        bid = f"b-{event_id}"
        (Path(data_dir) / "briefs").mkdir(parents=True, exist_ok=True)
        (Path(data_dir) / "briefs" / f"{bid}.md").write_text(
            f"# Event Alert\n\nTrigger: {event_id} / {ticker}\n"
        )
        store.insert_brief(
            conn, brief_id=bid, mode="event_alert", scope=ticker,
            generated_ts=_now(),
            content_path=f"briefs/{bid}.md",
            run_ids=[], parent_brief_id=None,
            trigger_event_id=event_id,
        )
        return bid
    sec.compose_event_alert = lambda **kw: fake_compose(
        kw["event_id"], kw["ticker"], kw["job_id"],
    )

    t0 = time.time()
    worker.drain_one(conn, secretary=sec)
    elapsed = time.time() - t0
    assert elapsed < 60, f"drain_one took {elapsed:.1f}s, expected < 60s"

    # Assertions
    job = conn.execute("SELECT * FROM queue_jobs WHERE trigger_event_id='ev1'").fetchone()
    assert job["state"] == "done"
    assert job["brief_id"] is not None

    brief = store.get_brief(conn, brief_id=job["brief_id"])
    assert brief is not None
    assert brief["trigger_event_id"] == "ev1"
    md_path = Path(data_dir) / brief["content_path"]
    assert md_path.exists()
    assert "AAPL" in md_path.read_text()

    # SLA assertion: brief_ts - event_ts < 60s
    ev = store.get_event(conn, event_id="ev1")
    latency = (
        datetime.fromisoformat(brief["generated_ts"].replace("Z", "+00:00"))
        - datetime.fromisoformat(ev["ingested_ts"].replace("Z", "+00:00"))
    ).total_seconds()
    assert latency < 60, f"latency {latency:.1f}s exceeded 60s CI bound"
