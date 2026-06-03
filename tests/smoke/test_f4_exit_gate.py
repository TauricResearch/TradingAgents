import json
from unittest.mock import MagicMock
import pytest

from tradingagents.persistence.db import connect
from tradingagents.persistence import store


@pytest.mark.smoke
def test_light_alert_approve_then_study(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    store.upsert_watchlist(conn, ticker="NVDA", ttl_until=None, tags=["user"])
    store.insert_event(conn, event_id="ev1", source="rss",
                       ingested_ts="2026-06-01T00:00:00+00:00", salience=0.9,
                       raw_path=None, status="triaged", deduped_of=None)
    store.insert_event_ticker(conn, event_id="ev1", ticker="NVDA", confidence=1.0)

    # 1) promoter composes the light alert (quick LLM mocked)
    from tradingagents.orchestrator.promoter import run_once
    from tradingagents.secretary.service import Secretary
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content="summary")
    sec = Secretary(conn=conn, data_dir=str(tmp_path / "data"), llm=llm)
    n = run_once(conn, salience_threshold=0.85, ticker_conf_threshold=0.9,
                 batch_size=50, cooldown_min=60, secretary=sec,
                 approval_gate_enabled=True, pending_ttl_hours=24)
    assert n == 1
    light = conn.execute("SELECT brief_id FROM briefs WHERE mode='event_alert_light'").fetchone()
    assert light is not None
    assert conn.execute("SELECT COUNT(*) FROM queue_jobs").fetchone()[0] == 0

    # 2) approve via the store transition the CLI/bot would do
    aid = conn.execute("SELECT action_id FROM brief_actions").fetchone()[0]
    store.update_action_state(conn, action_id=aid, state="accepted",
                              responded_at="2026-06-01T00:01:00+00:00")

    # 3) action-handler enqueues the heavy study
    from tradingagents.orchestrator.action_handler import tick
    tick(conn=conn, secretary=MagicMock(), dispatch_backtest=MagicMock())
    job = conn.execute("SELECT payload FROM queue_jobs").fetchone()
    assert json.loads(job["payload"]) == {"event_id": "ev1", "ticker": "NVDA"}
