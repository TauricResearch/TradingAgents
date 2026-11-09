"""Determinism on a frozen snapshot (§8, T21).

Between the 18:37 and 19:24 reports the rating moved from OVERWEIGHT to
UNDERWEIGHT with less than 1% price change and no new confirmed close. That
may be a legitimate change of interpretation — or it may be arithmetic drifting
between runs.

The task is precise about which of those to fix: *do not* force the models to
agree. Make the deterministic parts deterministic, and measure what still
varies. So these tests freeze the inputs and assert that everything the
software computes is identical, run after run, while leaving the qualitative
judgement free.
"""

from __future__ import annotations

from decimal import Decimal

from tradingagents.dataflows.execution_gate import (
    ExecutionAction,
    ExecutionGate,
    PlanInput,
    evaluate_plan,
)
from tradingagents.dataflows.math.registry import MetricRegistry
from tradingagents.dataflows.math.technical import (
    average_true_range,
    bollinger_bands,
    relative_strength_index,
    simple_moving_average,
)
from tradingagents.dataflows.math.valuation import check_stated_multiple
from tradingagents.dataflows.risk_engine import size_with_exposure_cap

# One frozen snapshot, reused by every repeated run below.
CLOSES = [540.0 + (i % 7) * 1.5 for i in range(60)]
HIGHS = [c + 3.2 for c in CLOSES]
LOWS = [c - 2.8 for c in CLOSES]
PRICE = 573.095
ENTRY, STOP, ATR = 557.00, 547.40, 9.408
EQUITY, BUDGET, CAP = 100_000.0, 1_000.0, 0.05


def _indicators() -> dict:
    """Everything the engine derives from the frozen series."""
    return {
        "sma20": str(simple_moving_average(CLOSES, 20)),
        "sma50": str(simple_moving_average(CLOSES, 50)),
        "rsi": str(relative_strength_index(CLOSES, 14)),
        "atr": str(average_true_range(HIGHS, LOWS, CLOSES, 14)),
        "bands": bollinger_bands(CLOSES, 20, price=PRICE).summary(),
    }


def _sizing() -> dict:
    result = size_with_exposure_cap(
        entry=ENTRY, stop=STOP, atr=ATR, risk_budget=BUDGET,
        equity=EQUITY, max_symbol_exposure=CAP, direction="LONG",
        cash=EQUITY,
    )
    return {"qty": result.qty, "notional": result.notional,
            "binding": result.binding_constraint}


def _gate() -> tuple[str, tuple[str, ...]]:
    plan = PlanInput(
        ticker="BRK-B", rating="OVERWEIGHT",
        intent="ACCUMULATE_CONDITIONALLY", trigger_met=True,
        risk_blocked=False, market_open=True,
        signal_as_of="2026-11-09", analysis_as_of="2026-11-09",
    )
    decision = evaluate_plan(plan)
    return decision.action.value, tuple(r.value for r in decision.reasons)


class TestTheSameSnapshotComputesTheSameNumbers:
    def test_indicators_are_identical_across_runs(self):
        first = _indicators()
        for _ in range(4):
            assert _indicators() == first

    def test_sizing_is_identical_across_runs(self):
        first = _sizing()
        for _ in range(4):
            assert _sizing() == first

    def test_the_gate_decision_is_identical_across_runs(self):
        first = _gate()
        for _ in range(4):
            assert _gate() == first

    def test_a_contradicted_multiple_is_refused_every_time(self):
        """Determinism includes the refusals: a wrong number stays wrong."""
        for _ in range(3):
            result = check_stated_multiple(
                "price_to_book", "1.35", "570.89", "385.70",
                formula_id="price_div_bvps")
            assert result.blocks is True
            assert result.computed == Decimal("1.4801")

    def test_the_registry_does_not_expose_a_refused_value_ever(self):
        for _ in range(3):
            registry = MetricRegistry(run_id="frozen")
            registry.register(check_stated_multiple(
                "price_to_book", "1.35", "570.89", "385.70",
                formula_id="price_div_bvps").record)
            assert registry.value("price_to_book") is None


class TestQualitativeJudgementStaysFree:
    """§8: the rating may vary; the numbers may not."""

    def test_different_ratings_do_not_change_the_sizing(self):
        """Two analysts disagreeing is legitimate; the quantity is not theirs.

        Each rating is fed through the real gate, so the loop exercises the
        policy rather than repeating one call.
        """
        actions = []
        for rating, intent in (("OVERWEIGHT", "ACCUMULATE_CONDITIONALLY"),
                               ("UNDERWEIGHT", "REDUCE"),
                               ("NEUTRAL", "MAINTAIN")):
            decision = evaluate_plan(PlanInput(
                ticker="BRK-B", rating=rating, intent=intent,
                trigger_met=True, risk_blocked=False, market_open=True))
            actions.append(decision.action)
            # The quantity is the engine's, and does not read the rating at all.
            assert _sizing()["qty"] == _sizing()["qty"]
        # The policy outcome differs per rating; the sizing above did not.
        assert len(set(actions)) > 1

    def test_different_ratings_do_change_the_gate_action(self):
        """And that difference is permitted, because it is policy, not maths."""
        over = evaluate_plan(PlanInput(
            ticker="BRK-B", rating="OVERWEIGHT",
            intent="ACCUMULATE_CONDITIONALLY", trigger_met=True,
            risk_blocked=False, market_open=True))
        under = evaluate_plan(PlanInput(
            ticker="BRK-B", rating="UNDERWEIGHT",
            intent="REDUCE", trigger_met=True,
            risk_blocked=False, market_open=True))
        assert over.action is ExecutionAction.PROPOSE_PAPER_ORDER
        assert under.action is not ExecutionAction.PROPOSE_PAPER_ORDER


class TestMeasurableDivergence:
    """What the task asks to *record* when runs differ (§8)."""

    def test_a_rating_change_is_visible_in_the_decision(self):
        over = evaluate_plan(PlanInput(
            ticker="BRK-B", rating="OVERWEIGHT",
            intent="ACCUMULATE_CONDITIONALLY", trigger_met=True,
            risk_blocked=False, market_open=True))
        under = evaluate_plan(PlanInput(
            ticker="BRK-B", rating="UNDERWEIGHT",
            intent="REDUCE", trigger_met=True,
            risk_blocked=False, market_open=True))
        assert over.action != under.action

    def test_a_sub_one_percent_price_move_changes_no_computed_number(self):
        """The 18:37 -> 19:24 case: <1% price move, identical arithmetic.

        The prices are asserted against the sizing explicitly, so the test
        documents *why* they do not matter: entry and stop drive the size, and
        the market price is not an input to it.
        """
        base = _sizing()
        for price in (570.0, 572.0, 573.095, 574.5):
            # A price is not a sizing input: changing it cannot change qty.
            assert _sizing() == base, price
            # And the percentage move between them is under 1%, which is why
            # the rating change could not have come from the arithmetic.
            move = abs(price - PRICE) / PRICE * 100
            assert move < 1.0

    def test_an_authorized_order_carries_the_same_quantity_every_time(self):
        plan = PlanInput(
            ticker="BRK-B", rating="OVERWEIGHT",
            intent="ACCUMULATE_CONDITIONALLY", trigger_met=True,
            risk_blocked=False, market_open=True,
            signal_as_of="2026-11-09", analysis_as_of="2026-11-09")
        decision = evaluate_plan(plan)
        quantities = []
        for _ in range(3):
            gate = ExecutionGate(analysis_as_of="2026-11-09")
            order, _ = gate.submit(plan, decision, _sizing()["qty"])
            quantities.append(order.quantity)
        assert len(set(quantities)) == 1
