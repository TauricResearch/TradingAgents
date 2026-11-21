"""FR-04 action, quantity and numeric-legality cases (22)."""

from __future__ import annotations

import pytest
from cases import ACT_CASES
from fakes import assert_case, build_case

CASES = ACT_CASES


@pytest.mark.parametrize("case", CASES, ids=[case.test_id for case in CASES])
def test_actions_and_quantities(case, gate_factory):
    case_input = build_case(case)
    harness = gate_factory(
        policy=case_input.policy,
        initial_portfolio=case_input.portfolio,
    )
    assert_case(case, harness, case_input)
