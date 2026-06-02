import json
from unittest.mock import MagicMock
import pytest

from tradingagents.persistence.db import connect
from tradingagents.persistence import store


def _now() -> str:
    return "2026-06-01T00:00:00+00:00"


@pytest.fixture
def conn(tmp_path):
    c = connect(str(tmp_path / "iic.db"))
    store.upsert_watchlist(c, ticker="NVDA", ttl_until=None, tags=["user"])
    store.upsert_watchlist(c, ticker="PANW", ttl_until=None, tags=["user"])
    return c


def _seed_event(conn):
    store.insert_event(conn, event_id="ev1", source="rss", ingested_ts=_now(),
                       salience=0.9, raw_path=None, status="triaged",
                       deduped_of=None)
    store.insert_event_ticker(conn, event_id="ev1", ticker="NVDA", confidence=1.0)
    store.insert_event_ticker(conn, event_id="ev1", ticker="PANW", confidence=1.0)


@pytest.mark.unit
def test_run_once_gate_composes_one_light_alert_no_queue_job(conn):
    from tradingagents.orchestrator.promoter import run_once
    _seed_event(conn)
    sec = MagicMock()
    sec.compose_event_alert_light.return_value = "lb1"

    n = run_once(conn, salience_threshold=0.85, ticker_conf_threshold=0.9,
                 batch_size=50, cooldown_min=60, secretary=sec,
                 approval_gate_enabled=True, pending_ttl_hours=24)

    assert n == 1
    sec.compose_event_alert_light.assert_called_once()
    _, kwargs = sec.compose_event_alert_light.call_args
    assert kwargs["event_id"] == "ev1"
    assert sorted(kwargs["tickers"]) == ["NVDA", "PANW"]
    # No heavy study enqueued at this stage.
    assert conn.execute("SELECT COUNT(*) FROM queue_jobs").fetchone()[0] == 0
