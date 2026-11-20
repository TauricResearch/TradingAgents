"""FR-04 transaction, concurrency, crash and audit-atomicity cases (24).

The tests treat the following test-only constructor seam as part of the D design:
``RiskGate(..., _fault_hook=callable)`` calls the hook at named stages
(``after_ledger_insert``, ``after_outbox_insert``, ``before_commit``). The hook is
used only to force deterministic crash/failure points. It is not exposed by the
public ``evaluate_and_commit`` signature.
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
from cases import ATM_CASES
from fakes import (
    base_evidence_pack,
    base_policy,
    base_portfolio,
    ledger_snapshot,
    make_policy,
    make_portfolio,
    make_proposal,
    reason_codes,
    status_of,
)

CASES = ATM_CASES
ROOT = Path(__file__).resolve().parents[3]
CRASH_CHILD = Path(__file__).with_name("_crash_child.py")


def _base_inputs():
    policy = base_policy()
    portfolio = base_portfolio()
    evidence = base_evidence_pack()
    proposal = make_proposal(policy=policy, evidence=evidence, portfolio=portfolio)
    return policy, portfolio, evidence, proposal


def _stale_version(case, gate_factory):
    policy, portfolio, evidence, proposal = _base_inputs()
    harness = gate_factory(policy=policy, initial_portfolio=portfolio)
    stale_portfolio = replace(portfolio, version=0)
    verdict = harness.gate.evaluate_and_commit(proposal, evidence, stale_portfolio)
    snapshot = ledger_snapshot(harness.db_path)
    assert status_of(verdict) == "REJECTED"
    assert "STALE_PORTFOLIO" in reason_codes(verdict)
    assert snapshot.ledger_count == 0
    assert snapshot.version == 1


def _version_increment(case, gate_factory):
    policy, portfolio, evidence, proposal = _base_inputs()
    harness = gate_factory(policy=policy, initial_portfolio=portfolio)
    verdict = harness.gate.evaluate_and_commit(proposal, evidence, portfolio)
    snapshot = ledger_snapshot(harness.db_path)
    assert status_of(verdict) == "APPROVED"
    assert snapshot.ledger_count == 1
    assert snapshot.version == 2
    assert snapshot.cash == Decimal("9899.90")


def _reject_no_version(case, gate_factory):
    policy, portfolio, evidence, _ = _base_inputs()
    proposal = make_proposal(
        policy=policy,
        evidence=evidence,
        portfolio=portfolio,
        quantity=1000,
    )
    harness = gate_factory(policy=policy, initial_portfolio=portfolio)
    verdict = harness.gate.evaluate_and_commit(proposal, evidence, portfolio)
    snapshot = ledger_snapshot(harness.db_path)
    assert status_of(verdict) == "REJECTED"
    assert snapshot.ledger_count == 0
    assert snapshot.version == 1
    assert snapshot.cash == Decimal("10000.00")


def _hold_no_version(case, gate_factory):
    policy, portfolio, evidence, _ = _base_inputs()
    proposal = make_proposal(
        policy=policy,
        evidence=evidence,
        portfolio=portfolio,
        action="HOLD",
    )
    harness = gate_factory(policy=policy, initial_portfolio=portfolio)
    verdict = harness.gate.evaluate_and_commit(proposal, evidence, portfolio)
    snapshot = ledger_snapshot(harness.db_path)
    assert status_of(verdict) == "APPROVED"
    assert snapshot.ledger_count == 0
    assert snapshot.version == 1
    assert snapshot.cash == Decimal("10000.00")


def _run_racing(gates, barrier, proposal, evidence, portfolio):
    def _run(harness):
        barrier.wait(timeout=10)
        return harness.gate.evaluate_and_commit(proposal, evidence, portfolio)

    with ThreadPoolExecutor(max_workers=len(gates)) as pool:
        futures = [pool.submit(_run, harness) for harness in gates]
        return [future.result(timeout=30) for future in futures]


def _two_concurrent_identical(case, gate_factory):
    policy, portfolio, evidence, proposal = _base_inputs()
    primary = gate_factory(policy=policy, initial_portfolio=portfolio)
    gates = [
        gate_factory(
            policy=policy,
            initial_portfolio=None,
            db_path=primary.db_path,
            busy_timeout_seconds=5.0,
        )
        for _ in range(2)
    ]
    results = _run_racing(gates, threading.Barrier(2), proposal, evidence, portfolio)
    snapshot = ledger_snapshot(primary.db_path)
    assert all(status_of(result) == "APPROVED" for result in results)
    assert len({result.verdict_id for result in results}) == 1
    assert snapshot.ledger_count == 1
    assert snapshot.version == 2
    assert snapshot.cash == Decimal("9899.90")


def _ten_concurrent_identical(case, gate_factory):
    policy, portfolio, evidence, proposal = _base_inputs()
    primary = gate_factory(policy=policy, initial_portfolio=portfolio)
    gates = [
        gate_factory(
            policy=policy,
            initial_portfolio=None,
            db_path=primary.db_path,
            busy_timeout_seconds=10.0,
        )
        for _ in range(10)
    ]
    results = _run_racing(gates, threading.Barrier(10), proposal, evidence, portfolio)
    snapshot = ledger_snapshot(primary.db_path)
    assert all(status_of(result) == "APPROVED" for result in results)
    assert len({result.verdict_id for result in results}) == 1
    assert snapshot.ledger_count == 1
    assert snapshot.version == 2
    assert snapshot.cash == Decimal("9899.90")


def _cash_for_one(case, gate_factory):
    policy = make_policy(fee_bps=0)
    portfolio = make_portfolio(
        cash="10000.00",
        positions=(("MSFT", 500, "100.00"),),
    )
    evidence = base_evidence_pack()
    first = make_proposal(
        policy=policy,
        evidence=evidence,
        portfolio=portfolio,
        proposal_id="proposal-a",
        quantity=60,
    )
    second = make_proposal(
        policy=policy,
        evidence=evidence,
        portfolio=portfolio,
        proposal_id="proposal-b",
        quantity=60,
    )
    primary = gate_factory(policy=policy, initial_portfolio=portfolio)
    gates = [
        gate_factory(
            policy=policy,
            initial_portfolio=None,
            db_path=primary.db_path,
            busy_timeout_seconds=5.0,
        )
        for _ in range(2)
    ]
    barrier = threading.Barrier(2)

    def _run(pair):
        harness, proposal = pair
        barrier.wait(timeout=10)
        return harness.gate.evaluate_and_commit(proposal, evidence, portfolio)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(_run, (gates[0], first)),
            pool.submit(_run, (gates[1], second)),
        ]
        results = [future.result(timeout=30) for future in futures]
    snapshot = ledger_snapshot(primary.db_path)
    statuses = {status_of(result) for result in results}
    assert "APPROVED" in statuses
    assert statuses <= {"APPROVED", "STALE_PORTFOLIO"}
    assert snapshot.ledger_count == 1
    assert snapshot.version == 2
    assert snapshot.cash == Decimal("4000.00")
    assert snapshot.cash >= Decimal("0")


def _concurrent_sells(case, gate_factory):
    policy = base_policy()
    portfolio = make_portfolio(
        cash="9000.00",
        positions=(("AAPL", 10, "100.00"),),
    )
    evidence = base_evidence_pack()
    first = make_proposal(
        policy=policy,
        evidence=evidence,
        portfolio=portfolio,
        proposal_id="sell-a",
        action="SELL",
        quantity=10,
    )
    second = make_proposal(
        policy=policy,
        evidence=evidence,
        portfolio=portfolio,
        proposal_id="sell-b",
        action="SELL",
        quantity=10,
    )
    primary = gate_factory(policy=policy, initial_portfolio=portfolio)
    gates = [
        gate_factory(
            policy=policy,
            initial_portfolio=None,
            db_path=primary.db_path,
            busy_timeout_seconds=5.0,
        )
        for _ in range(2)
    ]
    barrier = threading.Barrier(2)

    def _run(pair):
        harness, proposal = pair
        barrier.wait(timeout=10)
        return harness.gate.evaluate_and_commit(proposal, evidence, portfolio)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(_run, (gates[0], first)),
            pool.submit(_run, (gates[1], second)),
        ]
        results = [future.result(timeout=30) for future in futures]
    snapshot = ledger_snapshot(primary.db_path)
    assert sum(status_of(result) == "APPROVED" for result in results) == 1
    assert snapshot.ledger_count == 1
    assert snapshot.version == 2
    assert snapshot.cash == Decimal("9999.00")
    assert snapshot.positions == {}


def _concurrent_different(case, gate_factory):
    policy, portfolio, evidence, first = _base_inputs()
    second = make_proposal(
        policy=policy,
        evidence=evidence,
        portfolio=portfolio,
        proposal_id="proposal-2",
    )
    primary = gate_factory(policy=policy, initial_portfolio=portfolio)
    gates = [
        gate_factory(
            policy=policy,
            initial_portfolio=None,
            db_path=primary.db_path,
            busy_timeout_seconds=5.0,
        )
        for _ in range(2)
    ]
    barrier = threading.Barrier(2)

    def _run(pair):
        harness, proposal = pair
        barrier.wait(timeout=10)
        return harness.gate.evaluate_and_commit(proposal, evidence, portfolio)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(_run, (gates[0], first)),
            pool.submit(_run, (gates[1], second)),
        ]
        results = [future.result(timeout=30) for future in futures]
    snapshot = ledger_snapshot(primary.db_path)
    statuses = {status_of(result) for result in results}
    assert statuses == {"APPROVED", "STALE_PORTFOLIO"}
    assert snapshot.ledger_count == 1
    assert snapshot.version == 2
    assert snapshot.cash == Decimal("9899.90")


def _install_trigger(db_path, name, table, statement):
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            f"CREATE TRIGGER {name} BEFORE INSERT ON {table} "
            f"BEGIN SELECT RAISE(ABORT, '{statement}'); END"
        )
        connection.commit()
    finally:
        connection.close()


def _drop_trigger(db_path, name):
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(f"DROP TRIGGER {name}")
        connection.commit()
    finally:
        connection.close()


def _audit_failure(case, gate_factory):
    policy, portfolio, evidence, proposal = _base_inputs()
    harness = gate_factory(policy=policy, initial_portfolio=portfolio)
    _install_trigger(harness.db_path, "fail_outbox", "outbox_events", "audit unavailable")
    verdict = harness.gate.evaluate_and_commit(proposal, evidence, portfolio)
    snapshot = ledger_snapshot(harness.db_path)
    assert status_of(verdict) == "BLOCKED"
    assert "AUDIT_UNAVAILABLE" in reason_codes(verdict)
    assert snapshot.ledger_count == 0
    assert snapshot.verdict_count == 0
    assert snapshot.outbox_count == 0
    assert snapshot.cash == Decimal("10000.00")


def _crash_after_ledger(case, gate_factory):
    _run_crash_case(case, gate_factory, "after_ledger_insert")


def _crash_after_outbox(case, gate_factory):
    _run_crash_case(case, gate_factory, "after_outbox_insert")


def _run_crash_case(case, gate_factory, stage):
    policy, portfolio, _, _ = _base_inputs()
    harness = gate_factory(policy=policy, initial_portfolio=portfolio)
    result = subprocess.run(
        [
            sys.executable,
            str(CRASH_CHILD),
            "--db",
            str(harness.db_path),
            "--stage",
            stage,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 17, (result.returncode, result.stdout, result.stderr)
    snapshot = ledger_snapshot(harness.db_path)
    assert snapshot.ledger_count == 0
    assert snapshot.verdict_count == 0
    assert snapshot.outbox_count == 0
    assert snapshot.version == 1
    assert snapshot.cash == Decimal("10000.00")


def _db_locked(case, gate_factory):
    policy, portfolio, evidence, proposal = _base_inputs()
    primary = gate_factory(policy=policy, initial_portfolio=portfolio)
    blocker = sqlite3.connect(primary.db_path, timeout=0.0)
    try:
        blocker.execute("BEGIN EXCLUSIVE")
        locked = gate_factory(
            policy=policy,
            initial_portfolio=None,
            db_path=primary.db_path,
            busy_timeout_seconds=0.05,
        )
        verdict = locked.gate.evaluate_and_commit(proposal, evidence, portfolio)
        failed = ledger_snapshot(primary.db_path)
        assert status_of(verdict) == "BLOCKED"
        assert failed.ledger_count == 0
        assert failed.version == 1
    finally:
        blocker.execute("ROLLBACK")
        blocker.close()

    retry = gate_factory(
        policy=policy,
        initial_portfolio=None,
        db_path=primary.db_path,
        busy_timeout_seconds=5.0,
    )
    approved = retry.gate.evaluate_and_commit(proposal, evidence, portfolio)
    snapshot = ledger_snapshot(primary.db_path)
    assert status_of(approved) == "APPROVED"
    assert snapshot.ledger_count == 1
    assert snapshot.version == 2


def _outbox_ledger_atomic(case, gate_factory):
    policy, portfolio, evidence, proposal = _base_inputs()
    harness = gate_factory(policy=policy, initial_portfolio=portfolio)
    _install_trigger(harness.db_path, "fail_outbox", "outbox_events", "audit unavailable")
    verdict = harness.gate.evaluate_and_commit(proposal, evidence, portfolio)
    snapshot = ledger_snapshot(harness.db_path)
    assert status_of(verdict) == "BLOCKED"
    assert snapshot.ledger_count == 0
    assert snapshot.outbox_count == 0


def _verdict_ledger_atomic(case, gate_factory):
    policy, portfolio, evidence, proposal = _base_inputs()
    harness = gate_factory(policy=policy, initial_portfolio=portfolio)
    _install_trigger(harness.db_path, "fail_verdict", "risk_verdicts", "verdict unavailable")
    verdict = harness.gate.evaluate_and_commit(proposal, evidence, portfolio)
    snapshot = ledger_snapshot(harness.db_path)
    assert status_of(verdict) == "BLOCKED"
    assert snapshot.ledger_count == 0
    assert snapshot.verdict_count == 0
    assert snapshot.outbox_count == 0


def _sequence_gap_free(case, gate_factory):
    policy, portfolio, evidence, _ = _base_inputs()
    harness = gate_factory(policy=policy, initial_portfolio=portfolio)
    for index in range(3):
        current = harness.gate.snapshot()
        proposal = make_proposal(
            policy=policy,
            evidence=evidence,
            portfolio=current,
            proposal_id=f"proposal-{index}",
        )
        verdict = harness.gate.evaluate_and_commit(proposal, evidence, current)
        assert status_of(verdict) == "APPROVED"
    snapshot = ledger_snapshot(harness.db_path)
    sequences = [row[2] for row in snapshot.outbox_rows]
    assert sequences == [0, 1, 2]
    assert snapshot.ledger_count == 3
    assert snapshot.version == 4
    assert snapshot.cash == Decimal("9699.70")
    assert snapshot.positions == {"AAPL": 3}


def _hash_chain(case, gate_factory):
    policy, portfolio, evidence, _ = _base_inputs()
    harness = gate_factory(policy=policy, initial_portfolio=portfolio)
    for index in range(2):
        current = harness.gate.snapshot()
        proposal = make_proposal(
            policy=policy,
            evidence=evidence,
            portfolio=current,
            proposal_id=f"proposal-{index}",
        )
        verdict = harness.gate.evaluate_and_commit(proposal, evidence, current)
        assert status_of(verdict) == "APPROVED"
    snapshot = ledger_snapshot(harness.db_path)
    rows = snapshot.outbox_rows
    assert len(rows) == 2
    assert rows[0][4] == ""
    assert rows[1][4] == rows[0][3]
    for row in rows:
        assert len(row[3]) == 64
        assert len(row[4]) in {0, 64}
    assert snapshot.cash == Decimal("9799.80")
    assert snapshot.positions == {"AAPL": 2}


def _event_id_unique(case, gate_factory):
    policy, portfolio, evidence, proposal = _base_inputs()
    harness = gate_factory(policy=policy, initial_portfolio=portfolio)
    first = harness.gate.evaluate_and_commit(proposal, evidence, portfolio)
    second = harness.gate.evaluate_and_commit(proposal, evidence, portfolio)
    snapshot = ledger_snapshot(harness.db_path)
    assert status_of(first) == "APPROVED"
    assert status_of(second) == "APPROVED"
    assert first.verdict_id == second.verdict_id
    assert snapshot.ledger_count == 1
    assert snapshot.outbox_count == 1


def _review_no_ledger(case, gate_factory):
    policy, portfolio, _, proposal = _base_inputs()
    harness = gate_factory(policy=policy, initial_portfolio=portfolio)
    verdict = harness.gate.evaluate_and_commit(proposal, None, portfolio)
    snapshot = ledger_snapshot(harness.db_path)
    assert status_of(verdict) == "REVIEW"
    assert "EVIDENCE_MISSING" in reason_codes(verdict)
    assert snapshot.ledger_count == 0
    assert snapshot.version == 1
    assert snapshot.cash == Decimal("10000.00")


def _blocked_no_ledger(case, gate_factory):
    policy, portfolio, evidence, proposal = _base_inputs()
    harness = gate_factory(policy=None, initial_portfolio=portfolio)
    verdict = harness.gate.evaluate_and_commit(proposal, evidence, portfolio)
    snapshot = ledger_snapshot(harness.db_path)
    assert status_of(verdict) == "BLOCKED"
    assert "INCOMPATIBLE_STATE" in reason_codes(verdict)
    assert snapshot.ledger_count == 0
    assert snapshot.version == 1
    assert snapshot.cash == Decimal("10000.00")


def _concurrent_read(case, gate_factory):
    policy, portfolio, evidence, proposal = _base_inputs()
    entered = threading.Event()
    release = threading.Event()

    def hook(stage):
        if stage == "after_ledger_insert":
            entered.set()
            assert release.wait(10)

    harness = gate_factory(
        policy=policy,
        initial_portfolio=portfolio,
        _fault_hook=hook,
    )
    result_holder = {}

    def _run():
        result_holder["verdict"] = harness.gate.evaluate_and_commit(
            proposal, evidence, portfolio
        )

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    assert entered.wait(10), "gate did not reach after_ledger_insert"
    connection = sqlite3.connect(harness.db_path)
    try:
        version = connection.execute(
            "SELECT version FROM portfolios WHERE portfolio_id = 'portfolio-1'"
        ).fetchone()[0]
    finally:
        connection.close()
    assert version == 1
    release.set()
    thread.join(timeout=15)
    assert not thread.is_alive()
    snapshot = ledger_snapshot(harness.db_path)
    assert status_of(result_holder["verdict"]) == "APPROVED"
    assert snapshot.ledger_count == 1
    assert snapshot.version == 2


def _restart_after_success(case, gate_factory):
    policy, portfolio, evidence, proposal = _base_inputs()
    first_harness = gate_factory(policy=policy, initial_portfolio=portfolio)
    first = first_harness.gate.evaluate_and_commit(proposal, evidence, portfolio)
    second_harness = gate_factory(
        policy=policy,
        initial_portfolio=None,
        db_path=first_harness.db_path,
    )
    second = second_harness.gate.evaluate_and_commit(proposal, evidence, portfolio)
    snapshot = ledger_snapshot(first_harness.db_path)
    assert status_of(first) == "APPROVED"
    assert status_of(second) == "APPROVED"
    assert first.verdict_id == second.verdict_id
    assert snapshot.ledger_count == 1
    assert snapshot.version == 2
    assert snapshot.cash == Decimal("9899.90")


def _integrity_after_failure(case, gate_factory):
    policy, portfolio, evidence, proposal = _base_inputs()
    harness = gate_factory(policy=policy, initial_portfolio=portfolio)
    _install_trigger(harness.db_path, "fail_outbox", "outbox_events", "audit unavailable")
    verdict = harness.gate.evaluate_and_commit(proposal, evidence, portfolio)
    assert status_of(verdict) == "BLOCKED"
    connection = sqlite3.connect(harness.db_path)
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        connection.close()
    assert integrity == "ok"
    snapshot = ledger_snapshot(harness.db_path)
    assert snapshot.ledger_count == 0


def _commit_failure(case, gate_factory):
    policy, portfolio, evidence, proposal = _base_inputs()

    def hook(stage):
        if stage == "before_commit":
            raise RuntimeError("forced commit failure")

    harness = gate_factory(
        policy=policy,
        initial_portfolio=portfolio,
        _fault_hook=hook,
    )
    verdict = harness.gate.evaluate_and_commit(proposal, evidence, portfolio)
    snapshot = ledger_snapshot(harness.db_path)
    assert status_of(verdict) == "BLOCKED"
    assert snapshot.ledger_count == 0
    assert snapshot.verdict_count == 0
    assert snapshot.outbox_count == 0
    assert snapshot.cash == Decimal("10000.00")


ATM_SCENARIOS = {
    "stale_version": _stale_version,
    "version_increment": _version_increment,
    "reject_no_version": _reject_no_version,
    "hold_no_version": _hold_no_version,
    "two_concurrent_identical": _two_concurrent_identical,
    "ten_concurrent_identical": _ten_concurrent_identical,
    "cash_for_one": _cash_for_one,
    "concurrent_sells": _concurrent_sells,
    "concurrent_different": _concurrent_different,
    "audit_failure": _audit_failure,
    "crash_after_ledger": _crash_after_ledger,
    "crash_after_outbox": _crash_after_outbox,
    "db_locked": _db_locked,
    "outbox_ledger_atomic": _outbox_ledger_atomic,
    "verdict_ledger_atomic": _verdict_ledger_atomic,
    "sequence_gap_free": _sequence_gap_free,
    "hash_chain": _hash_chain,
    "event_id_unique": _event_id_unique,
    "review_no_ledger": _review_no_ledger,
    "blocked_no_ledger": _blocked_no_ledger,
    "concurrent_read": _concurrent_read,
    "restart_after_success": _restart_after_success,
    "integrity_after_failure": _integrity_after_failure,
    "commit_failure": _commit_failure,
}


@pytest.mark.parametrize("case", CASES, ids=[case.test_id for case in CASES])
def test_atomicity_and_concurrency(case, gate_factory):
    ATM_SCENARIOS[case.params["scenario"]](case, gate_factory)
