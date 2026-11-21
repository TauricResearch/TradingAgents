"""FR-04 evidence, time, expiry and policy-version cases (20)."""

from __future__ import annotations

import pytest
from cases import EVD_CASES
from fakes import assert_case, build_case

CASES = EVD_CASES


@pytest.mark.parametrize("case", CASES, ids=[case.test_id for case in CASES])
def test_evidence_time_and_policy(case, gate_factory):
    case_input = build_case(case)
    harness = gate_factory(
        policy=case_input.policy,
        initial_portfolio=case_input.portfolio,
    )
    assert_case(case, harness, case_input)
