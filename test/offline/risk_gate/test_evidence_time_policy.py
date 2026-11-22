"""FR-04 evidence, time, expiry and policy-version cases (20)."""

from __future__ import annotations

import pytest
from cases import EVD_CASES
from fakes import assert_case, build_case

CASES = EVD_CASES


def _assert_date_only_canonical(pack):
    from dataclasses import replace
    from datetime import date

    from egta.risk_gate.canonical import canonical_bytes, recompute_evidence_hash

    item = replace(pack.items[0], published_at=date(2026, 10, 1))
    date_pack = replace(pack, items=(item,))
    iso_pack = replace(pack, items=(replace(item, published_at="2026-10-01"),))
    assert b'"published_at":"2026-10-01"' in canonical_bytes(date_pack)
    assert recompute_evidence_hash(date_pack) == recompute_evidence_hash(iso_pack)


@pytest.mark.parametrize("case", CASES, ids=[case.test_id for case in CASES])
def test_evidence_time_and_policy(case, gate_factory):
    case_input = build_case(case)
    harness = gate_factory(
        policy=case_input.policy,
        initial_portfolio=case_input.portfolio,
    )
    assert_case(case, harness, case_input)
    if case.test_id == "T-RISK-EVD-05":
        _assert_date_only_canonical(case_input.evidence)
