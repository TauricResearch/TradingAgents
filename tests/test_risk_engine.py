"""Phase 2 — deterministic risk engine tests (contract section 5).

The BRK-B tranche/stop case (543.70 / 543.50 / ATR 9.408) is the regression
fixture: the plan must FAIL the buffer validation. Sizing, stress and
portfolio checks are pure functions with frozen numbers — no network, no
LLM, no live prices.
"""

from __future__ import annotations

import math

import pytest

from tests.fixtures.brk_b_2026_11_08 import (
    ATR_14,
    MIN_ENTRY_STOP_ATR,
    STOP_LOSS,
    TRANCHE_3_ENTRY,
    entry_stop_atr_multiple,
    entry_stop_distance,
)
from tradingagents.dataflows.risk_engine import (
    DEFAULT_MIN_ENTRY_STOP_ATR,
    RiskReason,
    RiskVerdict,
    portfolio_risk_check,
    size_position,
    stress_exit,
    validate_stop,
)

# ---------------------------------------------------------------------------
# Stop validation — the BRK-B regression case must fail (contract §5)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_brk_b_tranche_stop_plan_fails_the_buffer():
    """543.70 entry / 543.50 stop / ATR 9.408: ~0.021 ATR -> BLOCK.

    The contract requires this plan to fail validation; the fixture's
    arithmetic and the engine's must agree.
    """
    verdict = validate_stop(TRANCHE_3_ENTRY, STOP_LOSS, ATR_14,
                            min_atr=MIN_ENTRY_STOP_ATR)
    assert verdict.blocked
    assert verdict.reason is RiskReason.STOP_BUFFER_TOO_TIGHT
    assert verdict.distance == pytest.approx(entry_stop_distance())
    assert verdict.atr_multiple == pytest.approx(entry_stop_atr_multiple())
    assert verdict.atr_multiple < MIN_ENTRY_STOP_ATR


@pytest.mark.unit
def test_healthy_buffer_passes():
    """A stop one full ATR below the entry clears the 0.5 minimum."""
    verdict = validate_stop(100.0, 99.0, 1.0)
    assert not verdict.blocked
    assert verdict.reason is RiskReason.OK
    assert verdict.atr_multiple == pytest.approx(1.0)


@pytest.mark.unit
def test_buffer_exactly_at_minimum_passes():
    verdict = validate_stop(100.0, 99.5, 1.0, min_atr=0.5)
    assert not verdict.blocked


@pytest.mark.unit
def test_stop_at_or_above_entry_is_invalid_not_tight():
    """A stop that protects nothing is INVALID_STOP, a different failure."""
    for stop in (100.0, 101.0):
        verdict = validate_stop(100.0, stop, 1.0)
        assert verdict.blocked
        assert verdict.reason is RiskReason.INVALID_STOP


@pytest.mark.unit
def test_nonpositive_or_nonfinite_inputs_fail_with_reasons():
    cases = [
        (0.0, 99.0, 1.0, RiskReason.INVALID_ENTRY),
        (-5.0, 99.0, 1.0, RiskReason.INVALID_ENTRY),
        (100.0, 0.0, 1.0, RiskReason.INVALID_STOP),
        (100.0, 99.0, 0.0, RiskReason.INVALID_ATR),
        (100.0, 99.0, -1.0, RiskReason.INVALID_ATR),
        (float("nan"), 99.0, 1.0, RiskReason.INVALID_ENTRY),
        (100.0, float("inf"), 1.0, RiskReason.INVALID_STOP),
    ]
    for entry, stop, atr, expected in cases:
        verdict = validate_stop(entry, stop, atr)
        assert verdict.blocked
        assert verdict.reason is expected


@pytest.mark.unit
def test_minimum_buffer_is_parametric():
    """The 0.5 ATR default is a configuration, not a law (contract §5)."""
    assert DEFAULT_MIN_ENTRY_STOP_ATR == 0.5
    # A tighter plan passes under a relaxed threshold and fails under a
    # stricter one: the threshold moves the verdict, the arithmetic stands.
    relaxed = validate_stop(100.0, 99.8, 1.0, min_atr=0.1)
    strict = validate_stop(100.0, 99.8, 1.0, min_atr=1.0)
    assert not relaxed.blocked
    assert strict.blocked


# ---------------------------------------------------------------------------
# Gap / slippage stress — a stop is not a guaranteed price
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_stressed_exit_is_below_the_stop():
    stressed = stress_exit(100.0, 99.0, 1.0, gap_atr=0.5, slippage_pct=0.0005)
    assert stressed.stressed_exit < stressed.stop
    assert stressed.extra_loss_per_share == pytest.approx(0.5 + 0.05)
    assert stressed.is_guaranteed is False


@pytest.mark.unit
def test_zero_stress_reduces_to_the_nominal_stop():
    stressed = stress_exit(100.0, 99.0, 1.0, gap_atr=0.0, slippage_pct=0.0)
    assert stressed.stressed_exit == pytest.approx(99.0)
    assert stressed.extra_loss_per_share == 0.0


@pytest.mark.unit
def test_negative_stress_inputs_are_clamped_not_inverted():
    """A negative gap/slippage must not *raise* the exit above the stop."""
    stressed = stress_exit(100.0, 99.0, 1.0, gap_atr=-1.0, slippage_pct=-0.1)
    assert stressed.stressed_exit == pytest.approx(99.0)
    assert stressed.extra_loss_per_share == 0.0


# ---------------------------------------------------------------------------
# Sizing — deterministic, budget-driven, fail-closed
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_sizing_uses_stressed_risk_not_nominal():
    """qty = floor(budget / stressed_risk_per_share), smaller than nominal."""
    result = size_position(100.0, 99.0, 1.0, risk_budget=1000.0,
                           gap_atr=0.5, slippage_pct=0.0)
    stressed_risk = 100.0 - (99.0 - 0.5)
    assert result.stressed_risk_per_share == pytest.approx(stressed_risk)
    assert result.qty == math.floor(1000.0 / stressed_risk)
    assert result.qty < math.floor(1000.0 / 1.0)  # tighter than nominal sizing
    assert result.is_sizable


@pytest.mark.unit
def test_missing_budget_blocks_sizing():
    """No budget -> qty 0 with RISK_BUDGET_MISSING: never size without one."""
    result = size_position(100.0, 99.0, 1.0, risk_budget=None)
    assert result.qty == 0
    assert not result.is_sizable
    assert result.reasons == (RiskReason.RISK_BUDGET_MISSING,)


@pytest.mark.unit
def test_nonpositive_budget_blocks_sizing():
    for budget in (0.0, -100.0, float("nan"), float("inf")):
        result = size_position(100.0, 99.0, 1.0, risk_budget=budget)
        assert result.qty == 0
        assert RiskReason.RISK_BUDGET_MISSING in result.reasons


@pytest.mark.unit
def test_blocked_stop_short_circuits_sizing():
    """The BRK-B plan yields no size at all: the stop verdict leads."""
    result = size_position(TRANCHE_3_ENTRY, STOP_LOSS, ATR_14,
                           risk_budget=10_000.0, min_atr=MIN_ENTRY_STOP_ATR)
    assert result.qty == 0
    assert result.reasons == (RiskReason.STOP_BUFFER_TOO_TIGHT,)


@pytest.mark.unit
def test_budget_too_small_for_one_share_is_non_positive_size():
    result = size_position(100.0, 99.0, 1.0, risk_budget=0.5,
                           gap_atr=0.0, slippage_pct=0.0)
    assert result.qty == 0
    assert result.reasons == (RiskReason.NON_POSITIVE_SIZE,)


@pytest.mark.unit
def test_cash_constraint_blocks_when_notional_exceeds_it():
    result = size_position(100.0, 99.0, 1.0, risk_budget=10_000.0,
                           cash=500.0, gap_atr=0.0, slippage_pct=0.0)
    assert result.qty == 0
    assert result.reasons == (RiskReason.CASH_EXCEEDED,)


@pytest.mark.unit
def test_cash_constraint_passes_when_notional_fits():
    """Budget 1,000 at risk 1/share -> 1,000 shares = 100,000 notional, fits."""
    result = size_position(100.0, 99.0, 1.0, risk_budget=1_000.0,
                           cash=100_000.0, gap_atr=0.0, slippage_pct=0.0)
    assert result.qty == 1_000
    assert result.reasons == ()


@pytest.mark.unit
def test_planned_risk_never_exceeds_the_budget():
    result = size_position(100.0, 99.0, 1.0, risk_budget=250.0,
                           gap_atr=0.5, slippage_pct=0.0005)
    assert result.planned_risk <= 250.0 + 1e-9


# ---------------------------------------------------------------------------
# Portfolio-level risk — no equity, no fraction (contract §5)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_unknown_equity_blocks_and_keeps_fraction_none():
    """Without equity the fraction stays None: no invented base (DEF-005)."""
    check = portfolio_risk_check(planned_risk=2280.0, equity=None)
    assert check.blocked
    assert check.reasons == (RiskReason.PORTFOLIO_CONTEXT_MISSING,)
    assert check.max_portfolio_loss_fraction is None
    assert check.planned_risk_pct_equity is None


@pytest.mark.unit
def test_known_equity_yields_the_fraction():
    check = portfolio_risk_check(planned_risk=2280.0, equity=100_000.0)
    assert not check.blocked
    assert check.planned_risk_pct_equity == pytest.approx(0.0228)
    assert check.reasons == (RiskReason.OK,)


@pytest.mark.unit
def test_fraction_beyond_the_limit_blocks():
    check = portfolio_risk_check(planned_risk=5000.0, equity=100_000.0,
                                 max_loss_fraction=0.02)
    assert check.blocked
    assert check.reasons == (RiskReason.RISK_BUDGET_EXCEEDED,)


@pytest.mark.unit
def test_fraction_within_the_limit_passes():
    check = portfolio_risk_check(planned_risk=1500.0, equity=100_000.0,
                                 max_loss_fraction=0.02)
    assert not check.blocked


@pytest.mark.unit
def test_missing_planned_risk_with_known_equity_is_budget_missing():
    """No planned risk with known equity: RISK_BUDGET_MISSING, and blocked —
    the Gate cannot authorize a plan whose risk was never computed."""
    check = portfolio_risk_check(planned_risk=None, equity=100_000.0)
    assert check.reasons == (RiskReason.RISK_BUDGET_MISSING,)
    assert check.blocked


@pytest.mark.unit
def test_verdict_enum_is_stable_for_the_gate():
    """The Execution Gate (Phase 3) reads these names; they must not drift."""
    assert {v.value for v in RiskVerdict} == {"VALID", "BLOCK"}
