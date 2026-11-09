"""Execution Gate chokepoint (§7): one producer of orders, and it can refuse.

The audit for §7 looked for a paper-broker adapter and found none: the only
thing that can create an order is ``ExecutionGate.submit``, which returns a
``PaperOrder`` record and never calls out. That is *safer* than the task
assumes but it moves the guarantee: what must hold is that the gate is the
sole producer, that its preconditions are enforced for every action, and that
a refusal yields nothing at all.

These tests pin that from the outside — by searching the source tree for any
other order-producing path — and from the inside, by driving each refusal
case through the real objects.
"""

from __future__ import annotations

import re
from pathlib import Path

from tradingagents.dataflows.execution_gate import (
    ExecutionAction,
    ExecutionGate,
    GateReason,
    PaperOrder,
    PlanInput,
    evaluate_plan,
)


def _plan(**overrides) -> PlanInput:
    kwargs = {
        "ticker": "BRK-B",
        "rating": "OVERWEIGHT",
        "intent": "ACCUMULATE_CONDITIONALLY",
        "trigger_met": True,
        "risk_blocked": False,
        "risk_reasons": (),
        "data_quality_blocked": False,
        "post_event_status": "OBSERVABLE",
        "signal_as_of": "2026-11-09",
        "analysis_as_of": "2026-11-09",
        "market_open": True,
    }
    kwargs.update(overrides)
    return PlanInput(**kwargs)


class TestOneOrderProducer:
    """The gate is the only thing that can produce a paper order."""

    def test_paper_order_is_only_constructed_by_the_gate(self):
        """No module outside the gate creates a PaperOrder.

        This is the structural form of §7's requirement: a second constructor
        anywhere would be a bypass, however well-intentioned.
        """
        root = Path(__file__).resolve().parents[1] / "tradingagents"
        offenders = []
        for path in root.rglob("*.py"):
            if path.name == "execution_gate.py":
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if re.search(r"\bPaperOrder\s*\(", text):
                offenders.append(str(path.relative_to(root)))
        assert offenders == [], f"PaperOrder constructed outside the gate: {offenders}"

    def test_no_module_sends_an_order_to_a_venue(self):
        """There is no broker adapter to bypass — assert that stays true."""
        root = Path(__file__).resolve().parents[1] / "tradingagents"
        risky = re.compile(
            r"\b(?:submit_order|place_order|send_order|execute_order)\s*\(")
        offenders = []
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            if risky.search(text):
                offenders.append(str(path.relative_to(root)))
        assert offenders == [], (
            "an order-sending path exists and would need gate enforcement: "
            f"{offenders}"
        )

    def test_the_only_submit_is_the_gates_own(self):
        """``ExecutionGate.submit`` is reached, never re-implemented."""
        root = Path(__file__).resolve().parents[1] / "tradingagents"
        definitions = []
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            if re.search(r"def submit\s*\(", text):
                definitions.append(str(path.relative_to(root)))
        assert definitions == ["dataflows/execution_gate.py"]


class TestRefusalsProduceNothing:
    """Every refusal case yields no order object at all."""

    def _gate_and_quantity(self):
        return ExecutionGate(analysis_as_of="2026-11-09"), 8

    def test_a_blocked_plan_never_reaches_submit(self):
        gate, quantity = self._gate_and_quantity()
        decision = evaluate_plan(_plan(data_quality_blocked=True))
        assert decision.action is ExecutionAction.BLOCK
        assert decision.creates_order is False
        order, _reason = gate.submit(_plan(), decision, quantity)
        assert order is None
        assert gate.orders() == []

    def test_a_wait_plan_never_reaches_submit(self):
        gate, quantity = self._gate_and_quantity()
        decision = evaluate_plan(_plan(trigger_met=False))
        assert decision.action is ExecutionAction.WAIT
        order, _reason = gate.submit(_plan(trigger_met=False), decision, quantity)
        assert order is None
        assert gate.orders() == []

    def test_a_math_reason_blocks_regardless_of_the_trigger(self):
        gate, quantity = self._gate_and_quantity()
        decision = evaluate_plan(_plan(
            math_reasons=(GateReason.INVALID_PRICE_TO_BOOK,)))
        assert decision.action is ExecutionAction.BLOCK
        assert decision.creates_order is False

    def test_a_non_positive_quantity_is_refused(self):
        gate, _ = self._gate_and_quantity()
        decision = evaluate_plan(_plan())
        for bad in (0, -5):
            order, reason = gate.submit(_plan(), decision, bad)
            assert order is None
            assert reason is GateReason.RISK_PLAN_BLOCKED
        assert gate.orders() == []

    def test_a_stale_signal_is_refused_at_submission(self):
        """Revalidation happens at execution, not only when the plan was made."""
        gate = ExecutionGate(analysis_as_of="2026-11-09")
        decision = evaluate_plan(_plan())
        stale = _plan(signal_as_of="2026-11-06", analysis_as_of="2026-11-06")
        order, reason = gate.submit(stale, decision, 8)
        assert order is None
        assert reason is GateReason.STALE_SIGNAL

    def test_a_ticker_mismatch_is_refused(self):
        gate = ExecutionGate(analysis_as_of="2026-11-09")
        decision = evaluate_plan(_plan())
        other = _plan(ticker="AAPL")
        order, reason = gate.submit(other, decision, 8)
        assert order is None
        assert reason is GateReason.DATA_QUALITY_BLOCKED

    def test_no_refusal_ever_records_an_order(self):
        """The ledger stays empty across every refusal above."""
        gate = ExecutionGate(analysis_as_of="2026-11-09")
        blocked = evaluate_plan(_plan(data_quality_blocked=True))
        waiting = evaluate_plan(_plan(trigger_met=False))
        proposing = evaluate_plan(_plan())
        gate.submit(_plan(), blocked, 8)
        gate.submit(_plan(), waiting, 8)
        gate.submit(_plan(), proposing, 0)
        assert gate.orders() == []


class TestValidPathStillWorks:
    """The chokepoint must not block a sound proposal (§13 item 20)."""

    def test_a_valid_plan_produces_exactly_one_order(self):
        gate = ExecutionGate(analysis_as_of="2026-11-09")
        plan = _plan()
        decision = evaluate_plan(plan)
        assert decision.action is ExecutionAction.PROPOSE_PAPER_ORDER
        order, reason = gate.submit(plan, decision, 8)
        assert isinstance(order, PaperOrder)
        assert reason is GateReason.OK
        assert order.quantity == 8
        assert len(gate.orders()) == 1

    def test_a_retry_returns_the_original_and_creates_no_second(self):
        gate = ExecutionGate(analysis_as_of="2026-11-09")
        plan, decision = _plan(), evaluate_plan(_plan())
        first, _ = gate.submit(plan, decision, 8)
        second, reason = gate.submit(plan, decision, 8)
        assert second is first
        assert reason is GateReason.DUPLICATE_ORDER
        assert len(gate.orders()) == 1


class TestIntradayReactionBlocks:
    """§5 meets §7: an unsettled post-event reaction is a WAIT, not a proposal."""

    def test_an_intraday_reaction_cannot_propose_an_order(self):
        from tradingagents.dataflows.causal_guard import OBSERVABLE_INTRADAY

        decision = evaluate_plan(_plan(post_event_status=OBSERVABLE_INTRADAY))
        assert decision.creates_order is False
        assert any(r.value == "POST_EARNINGS_REACTION_UNOBSERVABLE"
                   for r in decision.reasons)

    def test_a_settled_reaction_can(self):
        decision = evaluate_plan(_plan(post_event_status="OBSERVABLE"))
        assert decision.action is ExecutionAction.PROPOSE_PAPER_ORDER
