"""FR-04 cash, holdings, concentration, notional, fee and slippage cases (24)."""

from __future__ import annotations

import pytest
from cases import FND_CASES
from fakes import assert_case, build_case

CASES = FND_CASES


@pytest.mark.parametrize("case", CASES, ids=[case.test_id for case in CASES])
def test_funds_positions_and_costs(case, gate_factory):
    case_input = build_case(case)
    harness = gate_factory(
        policy=case_input.policy,
        initial_portfolio=case_input.portfolio,
    )
    assert_case(case, harness, case_input)
