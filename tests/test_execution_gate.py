"""Phase 3 — Execution Gate tests (contract section 4).

The gate's core promise: WAIT and BLOCK create zero orders. The BRK-B
regression case (OVERWEIGHT rating, conditional plan, close above entry,
weekend release) must end in WAIT with no order. Idempotency: the same
plan key never yields two orders. Pure logic, frozen dates, no network.
"""

from __future__ import annotations

import pytest

from tradingagents.dataflows.causal_guard import NOT_YET_OBSERVABLE, OBSERVABLE
from tradingagents.dataflows.execution_gate import (
    ExecutionAction,
    ExecutionGate,
    GateDecision,
    GateReason,
    PlanInput,
    evaluate_plan,
)
from tradingagents.dataflows.risk_engine import RiskReason


def _plan(**overrides) -> PlanInput:
    """A plan that passes every check; overrides retarget any field."""
    kwargs = {
        "ticker": "BRK-B",
        "rating": "OVERWEIGHT",
        "intent": "ACCUMULATE_CONDITIONALLY",
        "trigger_met": True,
        "risk_blocked": False,
        "risk_reasons": (),
        "data_quality_blocked": False,
        "post_event_status": OBSERVABLE,
        "signal_as_of": "2026-11-09",
        "analysis_as_of": "2026-11-09",
        "market_open": True,
    }
    kwargs.update(overrides)
    return PlanInput(**kwargs)


# ---------------------------------------------------------------------------
# Vocabulary separation (contract §4: three distinct levels)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_overweight_rating_alone_never_executes():
    """OVERWEIGHT + MONITOR waits by policy: a rating is not an action."""
    decision = evaluate_plan(_plan(intent="MONITOR"))
    assert decision.action is ExecutionAction.WAIT
    assert not decision.creates_order


@pytest.mark.unit
def test_unknown_rating_or_intent_is_a_schema_block():
    for rating, intent in (("BUY", "ACCUMULATE_CONDITIONALLY"),
                           ("OVERWEIGHT", "BUY NOW")):
        decision = evaluate_plan(_plan(rating=rating, intent=intent))
        assert decision.action is ExecutionAction.BLOCK
        assert GateReason.DATA_QUALITY_BLOCKED in decision.reasons


@pytest.mark.unit
def test_overweight_with_met_trigger_proposes_but_does_not_submit():
    """A fully valid plan PROPOSEs; submission is a separate, revalidated step."""
    decision = evaluate_plan(_plan())
    assert decision.action is ExecutionAction.PROPOSE_PAPER_ORDER
    assert decision.creates_order  # a proposal, not yet an order


# ---------------------------------------------------------------------------
# The BRK-B regression case (contract §9, test 7)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_brk_b_weekend_case_waits_with_zero_orders():
    """OVERWEIGHT + conditional plan + unobservable reaction + trigger unmet.

    The report's own numbers: close 570.89 far above the 543.70 entry, the
    Q3 release published Saturday with no post-event session, run on Sunday.
    The gate must WAIT and no order may exist.
    """
    plan = _plan(
        trigger_met=False,                       # 570.89 > 543.70: not at entry
        post_event_status=NOT_YET_OBSERVABLE,    # Sat release, Sun run
        signal_as_of="2026-11-08",
        analysis_as_of="2026-11-08",
        market_open=False,                       # Sunday
    )
    decision = evaluate_plan(plan)
    assert decision.action is ExecutionAction.WAIT
    assert not decision.creates_order
    assert GateReason.ENTRY_TRIGGER_NOT_MET in decision.reasons
    assert GateReason.POST_EARNINGS_REACTION_UNOBSERVABLE in decision.reasons
    assert GateReason.MARKET_CLOSED in decision.reasons

    # And the gate refuses to submit on a WAIT decision:
    gate = ExecutionGate(analysis_as_of="2026-11-08")
    order, reason = gate.submit(plan, decision, quantity=100)
    assert order is None
    assert reason is GateReason.NO_TRIGGER


# ---------------------------------------------------------------------------
# Blocking paths
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_quarantined_data_blocks():
    decision = evaluate_plan(_plan(data_quality_blocked=True))
    assert decision.action is ExecutionAction.BLOCK
    assert GateReason.DATA_QUALITY_BLOCKED in decision.reasons


@pytest.mark.unit
def test_unobservable_reaction_blocks_even_with_trigger_met():
    """A reaction-based thesis with no post-event session is BLOCK, not WAIT."""
    decision = evaluate_plan(_plan(post_event_status=NOT_YET_OBSERVABLE))
    assert decision.action is ExecutionAction.BLOCK
    assert GateReason.POST_EARNINGS_REACTION_UNOBSERVABLE in decision.reasons


@pytest.mark.unit
def test_blocked_risk_plan_blocks_and_maps_reasons():
    decision = evaluate_plan(_plan(
        risk_blocked=True,
        risk_reasons=(RiskReason.STOP_BUFFER_TOO_TIGHT,),
    ))
    assert decision.action is ExecutionAction.BLOCK
    assert GateReason.RISK_PLAN_BLOCKED in decision.reasons


@pytest.mark.unit
def test_missing_portfolio_budget_maps_to_the_gate_reason():
    decision = evaluate_plan(_plan(
        risk_blocked=True,
        risk_reasons=(RiskReason.PORTFOLIO_CONTEXT_MISSING,),
    ))
    assert decision.action is ExecutionAction.BLOCK
    assert GateReason.PORTFOLIO_RISK_BUDGET_MISSING in decision.reasons


@pytest.mark.unit
def test_exceeded_portfolio_budget_maps_to_the_gate_reason():
    decision = evaluate_plan(_plan(
        risk_blocked=True,
        risk_reasons=(RiskReason.RISK_BUDGET_EXCEEDED,),
    ))
    assert decision.action is ExecutionAction.BLOCK
    assert GateReason.PORTFOLIO_RISK_BUDGET_EXCEEDED in decision.reasons


@pytest.mark.unit
def test_stale_signal_blocks():
    """A signal from before the analysis date is a historical report."""
    decision = evaluate_plan(_plan(signal_as_of="2026-11-06",
                                   analysis_as_of="2026-11-09"))
    assert decision.action is ExecutionAction.BLOCK
    assert GateReason.STALE_SIGNAL in decision.reasons


@pytest.mark.unit
def test_current_signal_is_not_stale():
    decision = evaluate_plan(_plan(signal_as_of="2026-11-09",
                                   analysis_as_of="2026-11-09"))
    assert GateReason.STALE_SIGNAL not in decision.reasons


@pytest.mark.unit
def test_closed_market_with_met_trigger_waits():
    """Market closed but plan otherwise valid: WAIT, not BLOCK."""
    decision = evaluate_plan(_plan(market_open=False))
    assert decision.action is ExecutionAction.WAIT
    assert GateReason.MARKET_CLOSED in decision.reasons


# ---------------------------------------------------------------------------
# Idempotent submission
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_submission_requires_a_proposal_decision():
    gate = ExecutionGate(analysis_as_of="2026-11-09")
    plan = _plan()
    for action in (ExecutionAction.WAIT, ExecutionAction.BLOCK):
        decision = GateDecision(action, (GateReason.OK,), plan.ticker)
        order, reason = gate.submit(plan, decision, quantity=10)
        assert order is None
        assert gate.orders() == []


@pytest.mark.unit
def test_valid_proposal_creates_exactly_one_order():
    gate = ExecutionGate(analysis_as_of="2026-11-09")
    plan = _plan()
    decision = evaluate_plan(plan)
    order, reason = gate.submit(plan, decision, quantity=100, limit_price=543.70)
    assert reason is GateReason.OK
    assert order is not None
    assert order.quantity == 100
    assert order.limit_price == 543.70
    assert len(gate.orders()) == 1


@pytest.mark.unit
def test_retry_with_same_plan_returns_the_original_order():
    """The contract's idempotency rule: a retry never duplicates an order."""
    gate = ExecutionGate(analysis_as_of="2026-11-09")
    plan = _plan()
    decision = evaluate_plan(plan)
    first, first_reason = gate.submit(plan, decision, quantity=100)
    second, second_reason = gate.submit(plan, decision, quantity=100)
    assert first_reason is GateReason.OK
    assert second_reason is GateReason.DUPLICATE_ORDER
    assert second is first
    assert len(gate.orders()) == 1


@pytest.mark.unit
def test_different_plans_get_different_keys_and_orders():
    gate = ExecutionGate(analysis_as_of="2026-11-09")
    decision_a = evaluate_plan(_plan(ticker="BRK-B"))
    decision_b = evaluate_plan(_plan(ticker="AAPL"))
    order_a, _ = gate.submit(_plan(ticker="BRK-B"), decision_a, quantity=10)
    order_b, _ = gate.submit(_plan(ticker="AAPL"), decision_b, quantity=5)
    assert order_a.idempotency_key != order_b.idempotency_key
    assert len(gate.orders()) == 2


@pytest.mark.unit
def test_submission_refuses_a_stale_signal():
    """Revalidation at execution time: a stale plan cannot submit."""
    gate = ExecutionGate(analysis_as_of="2026-11-09")
    plan = _plan(signal_as_of="2026-11-06", analysis_as_of="2026-11-09")
    decision = evaluate_plan(plan)  # BLOCKed anyway
    order, reason = gate.submit(plan, decision, quantity=10)
    assert order is None
    assert gate.orders() == []


@pytest.mark.unit
def test_submission_refuses_nonpositive_quantity():
    gate = ExecutionGate(analysis_as_of="2026-11-09")
    plan = _plan()
    decision = evaluate_plan(plan)
    for qty in (0, -5):
        order, reason = gate.submit(plan, decision, quantity=qty)
        assert order is None
        assert reason is GateReason.RISK_PLAN_BLOCKED
    assert gate.orders() == []


@pytest.mark.unit
def test_plan_key_is_stable_across_gate_instances():
    """Same inputs -> same key, so a restarted run cannot double-order."""
    plan = _plan()
    key_a = ExecutionGate(analysis_as_of="2026-11-09").plan_key(plan)
    key_b = ExecutionGate(analysis_as_of="2026-11-09").plan_key(plan)
    assert key_a == key_b
    # A different run date is a different plan.
    key_c = ExecutionGate(analysis_as_of="2026-11-10").plan_key(plan)
    assert key_a != key_c
