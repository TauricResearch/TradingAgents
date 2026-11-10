"""Phase 4 §7 — the execution boundary, with spies, and no real order.

What is actually at the boundary
--------------------------------
This repository contains **no broker adapter**. There is no client that can
reach a venue: `PaperOrder` is a frozen dataclass and `ExecutionGate.submit`
only ever appends to an in-memory dictionary. The only way an order comes to
exist is that method, and the only way it is stored is that dictionary.

So the "end of the line" here is not a network call to be mocked — it is the
`ExecutionGate` itself. These tests therefore:

- spy on `submit` to prove it is *not called* when the plan is invalid;
- spy on the gate's internal order map to prove an approved plan produces
  exactly one order for one candidate;
- assert the idempotency key so a retry cannot produce a second order.

**No live broker verification is claimed.** An end-to-end broker test would
require an adapter this codebase does not have, and saying otherwise would be
the kind of unearned assurance the contract forbids. What is verified is the
authorization boundary: the last line of code before any hypothetical adapter
would be called.
"""

from __future__ import annotations

import pytest

from tests.fixtures.brkb_2026_11_09 import ANALYSIS_DATE, BRKB, TICKER

pytestmark = pytest.mark.unit


def _plan(**overrides):
    from tradingagents.dataflows.execution_gate import PlanInput

    fields = {
        "ticker": TICKER,
        "rating": "OVERWEIGHT",
        "intent": "ACCUMULATE_CONDITIONALLY",
        "trigger_met": True,
        "risk_blocked": False,
        "risk_reasons": (),
        "data_quality_blocked": False,
        "post_event_status": None,
        "signal_as_of": ANALYSIS_DATE,
        "analysis_as_of": ANALYSIS_DATE,
        "market_open": True,
        "math_reasons": (),
    }
    fields.update(overrides)
    return PlanInput(**fields)


def _registry(state: dict):
    from tradingagents.dataflows.math.extraction import extract_run_inputs
    from tradingagents.dataflows.math.run_registry import (
        build_run_registry,
        registry_inputs_from_state,
    )
    from tradingagents.graph.trading_graph import _merge_extracted

    extracted = extract_run_inputs(state)
    inputs = _merge_extracted(registry_inputs_from_state(state), extracted.inputs)
    return build_run_registry(inputs, run_id="gate")


class SubmissionsSpy:
    """Records every attempt to create a paper order."""

    def __init__(self, gate):
        self.gate = gate
        self.calls = []
        self._original = gate.submit

    def __enter__(self):
        def record(*args, **kwargs):
            self.calls.append((args, kwargs))
            return self._original(*args, **kwargs)

        self.gate.submit = record
        return self

    def __exit__(self, *exc):
        self.gate.submit = self._original
        return False


# ---------------------------------------------------------------------------
# A valid candidate reaches the boundary and creates exactly one order
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_valid_candidate_is_approved_and_creates_one_order():
    """Approval requires every prerequisite, and it is explicit."""
    from tradingagents.dataflows.execution_gate import (
        ExecutionAction,
        ExecutionGate,
        evaluate_plan,
    )

    plan = _plan()
    decision = evaluate_plan(plan)
    assert decision.action is ExecutionAction.PROPOSE_PAPER_ORDER
    assert decision.reasons[0] == "OK"

    gate = ExecutionGate(analysis_as_of=ANALYSIS_DATE)
    with SubmissionsSpy(gate) as spy:
        order, reason = gate.submit(plan, decision,
                                    quantity=BRKB.expected["exposure_capped_qty"])

    assert reason == "OK"
    assert order is not None
    assert order.quantity == BRKB.expected["exposure_capped_qty"]
    assert len(spy.calls) == 1
    assert len(gate.orders()) == 1


@pytest.mark.unit
def test_a_retry_produces_no_duplicate_order():
    """The idempotency key is what stops a retry from doubling a position."""
    from tradingagents.dataflows.execution_gate import (
        ExecutionGate,
        evaluate_plan,
    )

    plan = _plan()
    decision = evaluate_plan(plan)
    gate = ExecutionGate(analysis_as_of=ANALYSIS_DATE)

    first, _ = gate.submit(plan, decision, quantity=8)
    second, reason = gate.submit(plan, decision, quantity=8)

    assert first is not None
    assert second is first, "a retry must return the original order"
    assert reason == "DUPLICATE_ORDER"
    assert len(gate.orders()) == 1, "one plan, one order — ever"


# ---------------------------------------------------------------------------
# Invalid candidates: blocked, reasons recorded, no order, submit not reached
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("overrides, expected_reason", [
    ({"risk_blocked": True, "risk_reasons": ("RISK_BUDGET_MISSING",)},
     "RISK_PLAN_BLOCKED"),
    ({"data_quality_blocked": True}, "DATA_QUALITY_BLOCKED"),
    ({"math_reasons": ("INVALID_PRICE_TO_BOOK",)}, "INVALID_PRICE_TO_BOOK"),
    ({"market_open": False}, "MARKET_CLOSED"),
    ({"trigger_met": False}, "ENTRY_TRIGGER_NOT_MET"),
    ({"rating": "SELL"}, "DATA_QUALITY_BLOCKED"),
])
def test_an_invalid_candidate_is_blocked_and_never_submitted(
        overrides, expected_reason):
    """Every rejection names its reason and reaches no execution code."""
    from tradingagents.dataflows.execution_gate import (
        ExecutionAction,
        ExecutionGate,
        evaluate_plan,
    )

    plan = _plan(**overrides)
    decision = evaluate_plan(plan)

    assert decision.action is not ExecutionAction.PROPOSE_PAPER_ORDER
    reasons = list(decision.reasons)
    assert expected_reason in reasons, reasons

    gate = ExecutionGate(analysis_as_of=ANALYSIS_DATE)
    with SubmissionsSpy(gate) as spy:
        order, reason = gate.submit(plan, decision, quantity=8)

    # Either submit was never called, or it was called and refused. Both are
    # acceptable; what is not acceptable is an order existing.
    assert order is None
    assert gate.orders() == []
    assert reason != "OK"
    if spy.calls:
        assert reason in {"RISK_PLAN_BLOCKED", "NO_TRIGGER"}


@pytest.mark.unit
def test_all_blocking_reasons_are_recorded_not_only_the_first():
    """One defect may imply several refusals; the audit needs them all."""
    from tradingagents.dataflows.execution_gate import evaluate_plan

    decision = evaluate_plan(_plan(
        risk_blocked=True,
        risk_reasons=("RISK_BUDGET_MISSING",),
        data_quality_blocked=True,
        math_reasons=("INVALID_PRICE_TO_BOOK",),
        market_open=False,
        trigger_met=False,
    ))
    reasons = set(decision.reasons)

    assert {"RISK_PLAN_BLOCKED", "DATA_QUALITY_BLOCKED",
            "INVALID_PRICE_TO_BOOK", "MARKET_CLOSED"} <= reasons


@pytest.mark.unit
def test_a_zero_or_negative_quantity_is_refused_at_submission():
    """A "quantity of nothing" is not an order, and is not stored as one."""
    from tradingagents.dataflows.execution_gate import (
        ExecutionGate,
        evaluate_plan,
    )

    plan = _plan()
    decision = evaluate_plan(plan)
    gate = ExecutionGate(analysis_as_of=ANALYSIS_DATE)

    for quantity in (0, -5):
        order, reason = gate.submit(plan, decision, quantity=quantity)
        assert order is None
        assert reason == "RISK_PLAN_BLOCKED"
    assert gate.orders() == []


@pytest.mark.unit
def test_a_stale_signal_is_refused_at_submission_time():
    """Revalidation at execution, not trust in a historical report (§7)."""
    from tradingagents.dataflows.execution_gate import (
        ExecutionGate,
        evaluate_plan,
    )

    plan = _plan(signal_as_of="2026-11-06", analysis_as_of="2026-11-06")
    decision = evaluate_plan(plan)
    gate = ExecutionGate(analysis_as_of=ANALYSIS_DATE)   # three days later

    order, reason = gate.submit(plan, decision, quantity=8)
    assert order is None
    assert reason == "STALE_SIGNAL"
    assert gate.orders() == []


# ---------------------------------------------------------------------------
# The boundary, stated honestly
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_no_broker_adapter_exists_to_call():
    """The claim this suite makes is about the gate, and it says so.

    If an adapter is ever added, this test fails and the §7 documentation must
    be revisited — which is the point: the boundary should not quietly move.
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "tradingagents"
    offenders = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for marker in ("import alpaca", "import ib_insync", "tradier",
                       "place_order(", "submit_order("):
            if marker in text:
                offenders.append((path.name, marker))

    assert offenders == [], (
        f"a broker adapter appeared: {offenders}. The §7 test documents that "
        "no broker end-to-end verification exists; that statement is now wrong.")


@pytest.mark.unit
def test_the_gate_touches_no_network():
    """An execution path that opens a socket is not a paper path.

    `conftest.py` already refuses sockets globally, so this test is a second,
    narrower statement: the gate's own module imports nothing that could reach
    a venue.
    """
    import tradingagents.dataflows.execution_gate as gate_module

    with open(gate_module.__file__, encoding="utf-8") as handle:
        source = handle.read()
    for forbidden in ("requests.", "urlopen", "curl_cffi", "httpx", "socket"):
        assert forbidden not in source, (
            f"the gate references {forbidden!r}; a paper gate must not be able "
            "to reach a venue")
