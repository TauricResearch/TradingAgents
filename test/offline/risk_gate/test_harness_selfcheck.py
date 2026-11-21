"""Two meta-tests proving the ``assert_case`` comparison harness is not vacuous.

A synthetic stub gate satisfies a synthetic case in one test and violates the same
case in the other. These tests do not import ``egta.risk_gate``; they remain green
while the implementation is absent.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest
from fakes import assert_case, base_evidence_pack, base_portfolio, base_proposal


class _StubGate:
    def __init__(self, db_path: str | Path, mutate: bool) -> None:
        self.db_path = Path(db_path)
        self.mutate = mutate

    def evaluate_and_commit(self, proposal, evidence, portfolio):
        if self.mutate:
            connection = sqlite3.connect(self.db_path)
            try:
                connection.execute(
                    "INSERT INTO ledger_entries (entry_id) VALUES ('entry-1')"
                )
                connection.execute(
                    "UPDATE portfolios SET version = 2, cash = '100.00' "
                    "WHERE portfolio_id = 'portfolio-1'"
                )
                connection.execute(
                    "INSERT INTO positions (portfolio_id, symbol, quantity, mark_price) "
                    "VALUES ('portfolio-1', 'AAPL', 1, '100.00')"
                )
                connection.commit()
            finally:
                connection.close()
        return SimpleNamespace(status="APPROVED", reasons=(), verdict_id="verdict-1")


def _make_db(path: str | Path) -> Path:
    db_path = Path(path)
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(
            """
            CREATE TABLE portfolios (
                portfolio_id TEXT PRIMARY KEY,
                version INTEGER NOT NULL,
                cash TEXT NOT NULL
            );
            CREATE TABLE positions (
                portfolio_id TEXT,
                symbol TEXT,
                quantity INTEGER,
                mark_price TEXT,
                PRIMARY KEY (portfolio_id, symbol)
            );
            CREATE TABLE ledger_entries (entry_id TEXT PRIMARY KEY);
            CREATE TABLE risk_verdicts (verdict_id TEXT PRIMARY KEY);
            CREATE TABLE outbox_events (
                event_id TEXT PRIMARY KEY,
                run_id TEXT,
                sequence INTEGER,
                payload_hash TEXT,
                prev_event_hash TEXT
            );
            INSERT INTO portfolios (portfolio_id, version, cash)
            VALUES ('portfolio-1', 1, '0.00');
            """
        )
        connection.commit()
    finally:
        connection.close()
    return db_path


def _synthetic_case() -> SimpleNamespace:
    return SimpleNamespace(
        test_id="T-HARNESS-01",
        expected_status="APPROVED",
        expected_reason=None,
        ledger_delta=1,
        version_delta=1,
        expected_cash="100.00",
        expected_positions={"AAPL": 1},
        expected_raw_positions=None,
    )


def _synthetic_input() -> SimpleNamespace:
    return SimpleNamespace(
        policy=None,
        portfolio=base_portfolio(),
        evidence=base_evidence_pack(),
        proposal=base_proposal(),
    )


def test_assert_case_accepts_a_satisfying_stub(tmp_path):
    db_path = _make_db(tmp_path / "satisfied.db")
    harness = SimpleNamespace(gate=_StubGate(db_path, mutate=True), db_path=db_path)
    assert_case(_synthetic_case(), harness, _synthetic_input())


def test_assert_case_rejects_a_violating_stub(tmp_path):
    db_path = _make_db(tmp_path / "violated.db")
    harness = SimpleNamespace(gate=_StubGate(db_path, mutate=False), db_path=db_path)
    with pytest.raises(AssertionError, match="ledger delta"):
        assert_case(_synthetic_case(), harness, _synthetic_input())
