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
    assert kwargs["deliver"] is True
    assert kwargs["ttl_hours"] == 24
    # No heavy study enqueued at this stage.
    assert conn.execute("SELECT COUNT(*) FROM queue_jobs").fetchone()[0] == 0


@pytest.mark.unit
def test_run_once_gate_requires_secretary(conn):
    from tradingagents.orchestrator.promoter import run_once
    _seed_event(conn)
    with pytest.raises(ValueError):
        run_once(conn, salience_threshold=0.85, ticker_conf_threshold=0.9,
                 batch_size=50, cooldown_min=60, secretary=None,
                 approval_gate_enabled=True, pending_ttl_hours=24)


@pytest.mark.unit
def test_run_once_gate_composes_one_alert_per_event(conn):
    """Distinct events with DISTINCT tickers each produce their own light alert.
    (When two events share a ticker, intra-batch dedup applies — covered by
    test_run_once_gate_dedups_ticker_within_one_pass.)"""
    from tradingagents.orchestrator.promoter import run_once
    _seed_event(conn)  # ev1: NVDA, PANW
    store.upsert_watchlist(conn, ticker="AMD", ttl_until=None, tags=["user"])
    store.insert_event(conn, event_id="ev2", source="rss", ingested_ts=_now(),
                       salience=0.9, raw_path=None, status="triaged",
                       deduped_of=None)
    store.insert_event_ticker(conn, event_id="ev2", ticker="AMD", confidence=1.0)
    sec = MagicMock()
    sec.compose_event_alert_light.return_value = "lb"
    n = run_once(conn, salience_threshold=0.85, ticker_conf_threshold=0.9,
                 batch_size=50, cooldown_min=60, secretary=sec,
                 approval_gate_enabled=True, pending_ttl_hours=24)
    assert n == 2
    assert sec.compose_event_alert_light.call_count == 2
    event_ids = sorted(c.kwargs["event_id"] for c in sec.compose_event_alert_light.call_args_list)
    assert event_ids == ["ev1", "ev2"]


@pytest.mark.unit
def test_run_once_gate_dedups_ticker_within_one_pass(conn):
    """Multiple events naming the SAME ticker in one batch must yield at most
    one light alert per ticker (intra-batch dedup). Regression for the 9x-NVDA
    duplicate-alert bug."""
    from tradingagents.orchestrator.promoter import run_once
    # three distinct events, all naming NVDA; ev2 also names PANW
    for i, tickers in enumerate([["NVDA"], ["NVDA", "PANW"], ["NVDA"]], start=1):
        ev = f"ev{i}"
        store.insert_event(conn, event_id=ev, source="rss", ingested_ts=_now(),
                           salience=0.9, raw_path=None, status="triaged",
                           deduped_of=None)
        for t in tickers:
            store.insert_event_ticker(conn, event_id=ev, ticker=t, confidence=1.0)
    store.upsert_watchlist(conn, ticker="PANW", ttl_until=None, tags=["user"])

    seen = []
    sec = MagicMock()
    def _capture(*, event_id, tickers, **kw):
        seen.append((event_id, sorted(tickers)))
        return f"lb_{event_id}"
    sec.compose_event_alert_light.side_effect = _capture

    run_once(conn, salience_threshold=0.85, ticker_conf_threshold=0.9,
             batch_size=50, cooldown_min=60, secretary=sec,
             approval_gate_enabled=True, pending_ttl_hours=24)

    # NVDA must appear in exactly ONE compose call across the whole pass
    nvda_calls = [s for s in seen if "NVDA" in s[1]]
    assert len(nvda_calls) == 1, seen
    # PANW (only on ev2) still gets alerted, bundled with NVDA on its event
    panw_calls = [s for s in seen if "PANW" in s[1]]
    assert len(panw_calls) == 1, seen
