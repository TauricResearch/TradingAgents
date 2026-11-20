"""FR-04 proposal identity and idempotent execution cases (18)."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from decimal import Decimal

import pytest
from cases import IDM_CASES
from fakes import (
    assert_case,
    base_evidence_pack,
    base_policy,
    base_portfolio,
    build_case,
    ledger_snapshot,
    make_proposal,
    reason_codes,
    status_of,
)

CASES = IDM_CASES


def _base_inputs():
    policy = base_policy()
    portfolio = base_portfolio()
    evidence = base_evidence_pack()
    proposal = make_proposal(policy=policy, evidence=evidence, portfolio=portfolio)
    return policy, portfolio, evidence, proposal


def _duplicate_approved(case, gate_factory):
    policy, portfolio, evidence, proposal = _base_inputs()
    harness = gate_factory(policy=policy, initial_portfolio=portfolio)
    first = harness.gate.evaluate_and_commit(proposal, evidence, portfolio)
    second = harness.gate.evaluate_and_commit(proposal, evidence, portfolio)
    snapshot = ledger_snapshot(harness.db_path)
    assert status_of(first) == "APPROVED"
    assert status_of(second) == "APPROVED"
    assert first.verdict_id == second.verdict_id
    assert snapshot.ledger_count == 1
    assert snapshot.version == 2
    assert snapshot.cash == Decimal(case.expected_cash)


def _duplicate_after_restart(case, gate_factory):
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


def _duplicate_rejected(case, gate_factory):
    policy, portfolio, evidence, _ = _base_inputs()
    proposal = make_proposal(
        policy=policy,
        evidence=evidence,
        portfolio=portfolio,
        quantity=1000,
    )
    harness = gate_factory(policy=policy, initial_portfolio=portfolio)
    first = harness.gate.evaluate_and_commit(proposal, evidence, portfolio)
    second = harness.gate.evaluate_and_commit(proposal, evidence, portfolio)
    snapshot = ledger_snapshot(harness.db_path)
    assert status_of(first) == "REJECTED"
    assert "POLICY_REJECTED" in reason_codes(first)
    assert status_of(second) == "REJECTED"
    assert first.verdict_id == second.verdict_id
    assert snapshot.ledger_count == 0
    assert snapshot.version == 1


def _duplicate_hold(case, gate_factory):
    policy, portfolio, evidence, _ = _base_inputs()
    proposal = make_proposal(
        policy=policy,
        evidence=evidence,
        portfolio=portfolio,
        action="HOLD",
    )
    harness = gate_factory(policy=policy, initial_portfolio=portfolio)
    first = harness.gate.evaluate_and_commit(proposal, evidence, portfolio)
    second = harness.gate.evaluate_and_commit(proposal, evidence, portfolio)
    snapshot = ledger_snapshot(harness.db_path)
    assert status_of(first) == "APPROVED"
    assert status_of(second) == "APPROVED"
    assert first.verdict_id == second.verdict_id
    assert snapshot.ledger_count == 0
    assert snapshot.version == 1


def _same_hash_different_id(case, gate_factory):
    policy, portfolio, evidence, proposal = _base_inputs()
    forged = replace(proposal, proposal_id="proposal-edited")
    harness = gate_factory(policy=policy, initial_portfolio=portfolio)
    verdict = harness.gate.evaluate_and_commit(forged, evidence, portfolio)
    snapshot = ledger_snapshot(harness.db_path)
    assert status_of(verdict) == "REJECTED"
    assert "INVALID_OUTPUT" in reason_codes(verdict)
    assert snapshot.ledger_count == 0
    assert snapshot.version == 1


def _duplicate_no_second_event(case, gate_factory):
    policy, portfolio, evidence, proposal = _base_inputs()
    harness = gate_factory(policy=policy, initial_portfolio=portfolio)
    harness.gate.evaluate_and_commit(proposal, evidence, portfolio)
    harness.gate.evaluate_and_commit(proposal, evidence, portfolio)
    snapshot = ledger_snapshot(harness.db_path)
    assert snapshot.ledger_count == 1
    assert snapshot.outbox_count == 1


def _retry_after_audit_failure(case, gate_factory):
    policy, portfolio, evidence, proposal = _base_inputs()
    harness = gate_factory(policy=policy, initial_portfolio=portfolio)
    connection = sqlite3.connect(harness.db_path)
    try:
        connection.execute(
            "CREATE TRIGGER fail_outbox BEFORE INSERT ON outbox_events "
            "BEGIN SELECT RAISE(ABORT, 'audit unavailable'); END"
        )
        connection.commit()
    finally:
        connection.close()

    blocked = harness.gate.evaluate_and_commit(proposal, evidence, portfolio)
    failed_snapshot = ledger_snapshot(harness.db_path)
    assert status_of(blocked) == "BLOCKED"
    assert "AUDIT_UNAVAILABLE" in reason_codes(blocked)
    assert failed_snapshot.ledger_count == 0
    assert failed_snapshot.verdict_count == 0
    assert failed_snapshot.outbox_count == 0

    connection = sqlite3.connect(harness.db_path)
    try:
        connection.execute("DROP TRIGGER fail_outbox")
        connection.commit()
    finally:
        connection.close()

    approved = harness.gate.evaluate_and_commit(proposal, evidence, portfolio)
    snapshot = ledger_snapshot(harness.db_path)
    assert status_of(approved) == "APPROVED"
    assert snapshot.ledger_count == 1
    assert snapshot.verdict_count == 1
    assert snapshot.outbox_count == 1
    assert snapshot.version == 2


def _different_payload_new_hash(case, gate_factory):
    policy, portfolio, evidence, proposal = _base_inputs()
    harness = gate_factory(policy=policy, initial_portfolio=portfolio)
    first = harness.gate.evaluate_and_commit(proposal, evidence, portfolio)
    assert status_of(first) == "APPROVED"
    current = ledger_snapshot(harness.db_path)
    second_portfolio = replace(portfolio, version=current.version)
    second_proposal = make_proposal(
        policy=policy,
        evidence=evidence,
        portfolio=second_portfolio,
        proposal_id="proposal-2",
    )
    second = harness.gate.evaluate_and_commit(second_proposal, evidence, second_portfolio)
    snapshot = ledger_snapshot(harness.db_path)
    assert status_of(second) == "APPROVED"
    assert second.proposal_hash != first.proposal_hash
    assert snapshot.ledger_count == 2
    assert snapshot.version == 3
    assert snapshot.cash == Decimal("9799.80")
    assert snapshot.positions == {"AAPL": 2}


IDM_SCENARIOS = {
    "duplicate_approved": _duplicate_approved,
    "duplicate_after_restart": _duplicate_after_restart,
    "duplicate_rejected": _duplicate_rejected,
    "duplicate_hold": _duplicate_hold,
    "same_hash_different_id": _same_hash_different_id,
    "duplicate_no_second_event": _duplicate_no_second_event,
    "retry_after_audit_failure": _retry_after_audit_failure,
    "different_payload_new_hash": _different_payload_new_hash,
}


@pytest.mark.parametrize("case", CASES, ids=[case.test_id for case in CASES])
def test_identity_and_idempotency(case, gate_factory):
    scenario = case.params.get("scenario")
    if scenario is None:
        case_input = build_case(case)
        harness = gate_factory(
            policy=case_input.policy,
            initial_portfolio=case_input.portfolio,
        )
        assert_case(case, harness, case_input)
        return
    IDM_SCENARIOS[scenario](case, gate_factory)
