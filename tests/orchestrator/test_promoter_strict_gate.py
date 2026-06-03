from dataclasses import dataclass
from unittest.mock import MagicMock

from tradingagents.persistence.db import connect
from tradingagents.persistence import store
from tradingagents.orchestrator.promoter import run_once


@dataclass
class EvalResult:
    passed: bool
    score: float
    payload: dict
    disqualifiers: list[str]


def seed_candidate(conn):
    store.upsert_watchlist(conn, ticker="NVDA", ttl_until=None, tags=["user"])
    store.insert_event(
        conn,
        event_id="ev1",
        source="rss",
        ingested_ts="2026-06-01T00:00:00+00:00",
        salience=0.95,
        raw_path=None,
        status="triaged",
        deduped_of=None,
    )
    store.insert_event_ticker(conn, event_id="ev1", ticker="NVDA", confidence=1.0)


def test_promoter_rejects_candidate_when_strict_gate_fails(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    seed_candidate(conn)
    secretary = MagicMock()

    n = run_once(
        conn,
        salience_threshold=0.85,
        ticker_conf_threshold=0.9,
        batch_size=50,
        cooldown_min=60,
        secretary=secretary,
        approval_gate_enabled=True,
        pending_ttl_hours=24,
        alert_evaluator=lambda event_id, tickers: EvalResult(
            passed=False,
            score=0.2,
            payload={"decision": "reject"},
            disqualifiers=["low_materiality"],
        ),
    )

    assert n == 0
    secretary.compose_event_alert_light.assert_not_called()


def test_promoter_composes_when_strict_gate_passes(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    seed_candidate(conn)
    secretary = MagicMock()

    n = run_once(
        conn,
        salience_threshold=0.85,
        ticker_conf_threshold=0.9,
        batch_size=50,
        cooldown_min=60,
        secretary=secretary,
        approval_gate_enabled=True,
        pending_ttl_hours=24,
        alert_evaluator=lambda event_id, tickers: EvalResult(
            passed=True,
            score=0.91,
            payload={"decision": "pass"},
            disqualifiers=[],
        ),
    )

    assert n == 1
    secretary.compose_event_alert_light.assert_called_once()
