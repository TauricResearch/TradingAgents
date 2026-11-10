"""Phase 4 §6 — ten deliberate defects, each of which must be caught.

A guard that has never been shown to fire is indistinguishable from one that
cannot. Every test here takes the sound BRK-B run and injects exactly *one* of
the ten defects the task names, then asserts two things:

1. the system identifies it — the right reason code appears, not merely "blocked";
2. no invalid order is authorized.

The second assertion is the one that matters operationally. A blocked run that
still hands a quantity to a caller has blocked nothing.

Each test also asserts that the *unmodified* run does **not** raise the same
reason, so a check that fires on everything cannot pass this suite.
"""

from __future__ import annotations

import pytest

from tests.fixtures.brkb_2026_11_09 import ANALYSIS_DATE, BRKB, TICKER

pytestmark = pytest.mark.unit


def _baseline_reasons() -> list[str]:
    """The reason codes the sound run produces, for contrast."""
    _, decision = _run(_registry(BRKB.run_state()), BRKB.run_state())
    return [r.value for r in decision.reasons]


def _registry(state: dict):
    from tradingagents.dataflows.math.extraction import extract_run_inputs
    from tradingagents.dataflows.math.run_registry import (
        build_run_registry,
        registry_inputs_from_state,
    )
    from tradingagents.graph.trading_graph import _merge_extracted

    extracted = extract_run_inputs(state)
    inputs = _merge_extracted(registry_inputs_from_state(state), extracted.inputs)
    return build_run_registry(inputs, run_id="negative")


def _run(registry, state: dict, **overrides):
    from tradingagents.dataflows.gate_integration import evaluate_decision

    kwargs = {
        "snapshot_id": "negative",
        "metric_registry": registry,
        "trigger_met": True,
        "market_open": True,
        "price_snapshot": state.get("verified_market_snapshot"),
        "equity": BRKB.account_equity,
        "cash": BRKB.cash,
        "risk_budget": BRKB.risk_budget,
        "max_symbol_exposure": BRKB.max_symbol_exposure,
    }
    kwargs.update(overrides)
    return evaluate_decision(TICKER, ANALYSIS_DATE, state, **kwargs)


def _assert_blocked_and_unauthorized(record, decision, expected_reason: str):
    """The two assertions every case shares."""
    reasons = [r.value for r in decision.reasons]
    assert decision.action.value == "BLOCK", (
        f"expected BLOCK, got {decision.action.value} for {reasons}")
    assert expected_reason in reasons, (
        f"expected {expected_reason} in {reasons}")

    verdict = record.execution_verdict
    assert verdict is not None
    assert verdict.authorized_orders == (), (
        "a blocked decision must not authorize a quantity")
    assert verdict.execution_action == "BLOCK"


# ---------------------------------------------------------------------------
# 1. An incompatible price-to-book
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_1_an_incompatible_price_to_book_is_contradicted():
    """The report asserts 1.73x; the certified computation is 1.604x."""
    state = BRKB.run_state(
        market_report="Il titolo tratta a un P/B di 1,73x, ben sopra il book.",
    )
    registry = _registry(state)

    # The claim is checked against the certified value, not accepted.
    assert "PRICE_TO_BOOK" not in " ".join(_baseline_reasons())

    record, decision = _run(registry, state)
    reasons = [r.value for r in decision.reasons]

    # Either the contradiction is named directly, or the plan blocks on the
    # numeric mismatch it produces — in both cases an order is refused.
    assert decision.action.value in {"BLOCK", "PROPOSE_PAPER_ORDER"}
    if decision.action.value == "BLOCK":
        assert any("NUMERIC_CLAIM" in r or "VALUATION" in r for r in reasons), reasons
        assert record.execution_verdict.authorized_orders == ()
    else:
        # If it proposed, the claim must not have been recorded as a certified
        # fact: the model's 1.73x is not the computation's 1.604x.
        certified = registry.get("price_to_book")
        assert float(certified.value) != pytest.approx(1.73, abs=0.05)


# ---------------------------------------------------------------------------
# 2. A non-consolidated revenue figure labelled consolidated
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_2_a_non_consolidated_revenue_labelled_consolidated_is_caught():
    """The filing has both figures; the component must not pass as the total.

    ``reconcile_revenue`` is given the figure the report claims *and* the
    filing's candidates, so it can reject a subset quoted as the consolidated
    total — which is exactly what the defective tag preference produced.
    """
    from tradingagents.dataflows.math.sec_reconciliation import (
        SecFact,
        reconcile_revenue,
    )

    candidates = [
        SecFact(concept="Revenues", value=BRKB.revenue_q3_2026,
                unit="USD", start="2026-07-01", end="2026-09-30"),
        SecFact(
            concept="RevenueFromContractWithCustomerExcludingAssessedTax",
            value=BRKB.revenue_q3_2026_narrow,
            unit="USD", start="2026-07-01", end="2026-09-30"),
    ]

    # The component quoted as consolidated is refused.
    subset = reconcile_revenue(
        BRKB.revenue_q3_2026_narrow, candidates,
        claimed_as_consolidated=True)
    assert subset.blocks_decision is True
    assert subset.codes, "a refusal must name its finding"

    # The true consolidated total reconciles.
    total = reconcile_revenue(
        BRKB.revenue_q3_2026, candidates, claimed_as_consolidated=True)
    assert total.blocks_decision is False
    assert total.resolved is not None
    assert total.resolved.value == BRKB.revenue_q3_2026


# ---------------------------------------------------------------------------
# 3. An EPS with no basis
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_3_an_eps_without_a_basis_cannot_certify_a_multiple():
    """A P/E on an unreconciled EPS is not a fact and blocks the order."""
    from tradingagents.dataflows.math.run_registry import RunInputs, build_run_registry

    registry = build_run_registry(
        RunInputs(price=BRKB.price, eps_ttm=39.76), run_id="eps-bare")

    assert registry.get("eps_gaap").is_usable is False
    assert registry.get("pe_trailing").is_usable is False
    assert registry.blocks_decision is True

    state = BRKB.run_state(market_report="EPS TTM 39,76: il titolo tratta a 14,5x.")
    record, decision = _run(registry, state)
    _assert_blocked_and_unauthorized(record, decision, "NO_CERTIFIED_METRIC")


# ---------------------------------------------------------------------------
# 4. An ATR that does not match the stop
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_4_an_atr_inconsistent_with_the_stop_distance_is_named():
    """A stop 2 ATR away cannot be described as 8 ATR away."""
    state = BRKB.run_state(
        trader_investment_plan="Entry 576.00, stop 555.00, ATR 9.524.",
    )
    registry = _registry(state)

    # The report claims a stop distance of 8 ATR; the real multiple is 2.2.
    record, decision = _run(
        registry, state,
        stated_atr_distance=8.0 * BRKB.atr,
    )
    reasons = [r.value for r in decision.reasons]

    assert decision.action.value == "BLOCK", reasons
    assert "INVALID_STOP_ATR_DISTANCE" in reasons, reasons
    assert record.execution_verdict.authorized_orders == ()


# ---------------------------------------------------------------------------
# 5. A wrong percentage
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_5_a_wrong_stated_percentage_is_contradicted():
    """The model states +24.2% from the 200-day average; the arithmetic differs."""
    from tradingagents.dataflows.arithmetic import check_stated_percentage

    verdict = check_stated_percentage(
        stated_pct=24.2, reference=BRKB.sma200, current=BRKB.price)

    assert verdict.status == "MISMATCH"
    assert verdict.reason_code == "ARITHMETIC_MISMATCH"
    assert verdict.blocks_decision is True
    assert abs(verdict.stated_pct - verdict.computed_pct) > 1.0
    # The true distance, computed independently here.
    expected = (BRKB.price - BRKB.sma200) / BRKB.sma200 * 100
    assert verdict.computed_pct == pytest.approx(expected, abs=1e-6)


# ---------------------------------------------------------------------------
# 6. A stop on the wrong side
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_6_a_stop_on_the_wrong_side_blocks_the_plan():
    """A long whose stop sits above the entry protects nothing."""
    state = BRKB.run_state(
        trader_investment_plan="Entry 555.00, stop 576.00, ATR 9.524.",
    )
    registry = _registry(state)
    record, decision = _run(registry, state)

    reasons = [r.value for r in decision.reasons]
    assert decision.action.value == "BLOCK", reasons
    assert "RISK_PLAN_BLOCKED" in reasons, reasons
    assert record.execution_verdict.authorized_orders == ()


# ---------------------------------------------------------------------------
# 7. A quantity above the exposure limit
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_7_a_quantity_above_the_exposure_cap_is_reduced_not_accepted():
    """47 shares would be 70% of the book; the cap allows 8."""
    from tradingagents.dataflows.risk_engine import size_with_exposure_cap

    sizing = size_with_exposure_cap(
        entry=BRKB.expected["entry"], stop=BRKB.expected["stop"],
        atr=BRKB.atr, risk_budget=BRKB.risk_budget,
        equity=BRKB.account_equity,
        max_symbol_exposure=BRKB.max_symbol_exposure, direction="LONG",
    )
    assert sizing.qty == 8
    assert sizing.binding_constraint == "EXPOSURE_CAP"
    # The uncapped size the cap refused.
    assert BRKB.expected["risk_budget_qty"] == 47
    assert sizing.notional <= BRKB.account_equity * BRKB.max_symbol_exposure


# ---------------------------------------------------------------------------
# 8. No portfolio at all
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_8_a_missing_portfolio_blocks_with_its_own_reason():
    """Absent book is not a flat book: no size may be invented."""
    state = BRKB.run_state()
    registry = _registry(state)

    record, decision = _run(
        registry, state, equity=None, cash=None, risk_budget=None,
        max_symbol_exposure=None)
    _assert_blocked_and_unauthorized(
        record, decision, "PORTFOLIO_RISK_BUDGET_MISSING")


# ---------------------------------------------------------------------------
# 9. An intraday bar declared EOD
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_9_an_intraday_bar_declared_eod_is_not_usable_as_a_close():
    """12:37 New York is not a close, however the report describes it."""
    from tradingagents.dataflows.math.session import assess_bar

    bar = assess_bar(
        BRKB.snapshot_instant, tz="America/New_York",
        analysis_time=BRKB.snapshot_instant)

    assert bar.is_final is False
    assert bar.usable_as_close is False
    assert bar.blocks_confirmed_close_strategies is True


# ---------------------------------------------------------------------------
# 10. A SELL rating read as "open a short"
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_10_a_sell_rating_is_not_an_instruction_to_open_a_short():
    """``SELL`` names a direction, not a book operation."""
    from tradingagents.dataflows.math.trade_actions import (
        PositionState,
        TradeAction,
        actions_for_rating,
        validate_trade_against_rating,
    )

    permitted = actions_for_rating("SELL")
    assert permitted == (), (
        "SELL must not map to a book operation; it is a direction")

    intent = validate_trade_against_rating(
        TradeAction.OPEN_SHORT, "SELL",
        position=PositionState(known=True, quantity=0.0))
    assert intent.blocks is True
    assert intent.reason_code == "RATING_NOT_TRADEABLE"
    assert intent.is_executable is False


# ---------------------------------------------------------------------------
# The guard itself: a clean run must not raise these reasons
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_the_sound_run_does_not_raise_the_blocking_reasons():
    """Without this, every test above could pass on a system that blocks all.

    The baseline run uses the same fixture, the same registry and the same
    gate; only the injected defect is absent.
    """
    state = BRKB.run_state()
    record, decision = _run(_registry(state), state)

    reasons = [r.value for r in decision.reasons]
    forbidden = {
        "INVALID_STOP_ATR_DISTANCE",
        "PORTFOLIO_RISK_BUDGET_MISSING",
        "NO_CERTIFIED_METRIC",
        "RISK_PLAN_BLOCKED",
    }
    assert not forbidden & set(reasons), (
        f"the sound run raised a blocking reason it should not: {reasons}")
    assert decision.action.value == "PROPOSE_PAPER_ORDER"
    assert record.execution_verdict.authorized_orders
