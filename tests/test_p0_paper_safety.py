"""P0 security: an unvalidated order cannot reach the paper broker.

The task's hard requirement: injecting an invalid order directly through
the execution path — bypassing every LLM component — must still be blocked,
and a mock broker must record zero orders whenever any critical check
fails.

These tests drive the real ``evaluate_decision`` -> ``ExecutionGate`` path
with a mock broker behind it, so the guarantee is about code, not prose.
"""

from __future__ import annotations

import json

import pytest

from tradingagents.dataflows.execution_gate import (
    ExecutionAction,
    ExecutionGate,
    GateDecision,
    GateReason,
)
from tradingagents.dataflows.gate_integration import evaluate_decision


class MockPaperBroker:
    """Records what would have been sent to a paper venue."""

    def __init__(self):
        self.sent: list[dict] = []

    def send(self, order) -> None:
        self.sent.append(order)


def _state(*, rating="Overweight", plan="", news="", fundamentals=""):
    return {
        "company_of_interest": "BRK-B",
        "trade_date": "2026-11-08",
        "market_report": "",
        "sentiment_report": "",
        "news_report": news,
        "fundamentals_report": fundamentals,
        "investment_debate_state": {"bull_history": "", "bear_history": "",
                                    "history": "", "current_response": ""},
        "trader_investment_plan": plan,
        "risk_debate_state": {"aggressive_history": "", "conservative_history": "",
                              "neutral_history": "", "history": ""},
        "investment_plan": "",
        "final_rating": rating,
        "final_trade_decision": f"**Rating**: {rating}\nPlan.",
    }


def _route_to_broker(record, decision, gate, broker, quantity):
    """The only path that could reach a venue: submit then send.

    Mirrors what any scheduler/API/agent path must do — the gate is the
    single chokepoint, so a blocked decision can never produce a send.
    """
    if not decision.creates_order:
        return None
    order, _reason = gate.submit(
        _plan_for(record), decision, quantity=quantity,
    )
    if order is not None:
        broker.send({"order_id": order.order_id, "qty": order.quantity})
    return order


def _plan_for(record):
    """Reconstruct the plan the gate evaluated, for submission revalidation."""
    from tradingagents.dataflows.execution_gate import PlanInput

    verdict = getattr(record, "execution_verdict", None)
    data = verdict.to_dict() if verdict is not None else {}
    return PlanInput(
        ticker=record.ticker,
        rating="OVERWEIGHT",
        intent="ACCUMULATE_CONDITIONALLY",
        trigger_met=data.get("execution_action") == ExecutionAction.PROPOSE_PAPER_ORDER.value,
        risk_blocked=False,
        risk_reasons=(),
        data_quality_blocked=False,
        post_event_status=None,
        signal_as_of=record.analysis_as_of,
        analysis_as_of=record.analysis_as_of,
        market_open=True,
    )


class TestNoOrderReachesTheBroker:
    def test_stale_fundamentals_send_zero_orders(self):
        from tradingagents.dataflows.filing_freshness import FilingRecord

        q2 = FilingRecord("2026-Q2", "2026-06-30", published_date="2026-08-02")
        q3 = FilingRecord("2026-Q3", "2026-09-30", published_date="2026-11-07")
        broker = MockPaperBroker()
        gate = ExecutionGate(analysis_as_of="2026-11-08")

        record, decision = evaluate_decision(
            "BRK-B", "2026-11-08",
            _state(plan="Entry 556.00, stop 542.50, ATR 9.408.",
                   fundamentals="Stockholders Equity: 747,910 USD million as of 2026-Q2."),
            snapshot_id="sec-1",
            fundamentals_filings=[q2, q3],
            used_fundamentals_period_end="2026-06-30",
            equity=100_000.0, risk_budget=1_000.0, max_symbol_exposure=0.05,
        )
        _route_to_broker(record, decision, gate, broker, quantity=8)

        assert decision.action is ExecutionAction.BLOCK
        assert broker.sent == []
        # The verdict states the reason, machine-readably.
        verdict = record.execution_verdict.to_dict()
        assert verdict["execution_approved"] is False
        assert verdict["authorized_orders"] == []

    def test_conflicting_agent_facts_send_zero_orders(self):
        broker = MockPaperBroker()
        gate = ExecutionGate(analysis_as_of="2026-11-08")

        record, decision = evaluate_decision(
            "BRK-B", "2026-11-08",
            _state(
                plan="Entry 556.00, stop 542.50, ATR 9.408.",
                news="Q3 2026 buyback of approximately $9.6 billion.",
                fundamentals="Q3 2026 Share Repurchases: 100 USD million.",
            ),
            snapshot_id="sec-2",
            equity=100_000.0, risk_budget=1_000.0, max_symbol_exposure=0.05,
        )
        _route_to_broker(record, decision, gate, broker, quantity=8)

        assert decision.action is ExecutionAction.BLOCK
        assert broker.sent == []

    def test_wrong_side_stop_sends_zero_orders(self):
        broker = MockPaperBroker()
        gate = ExecutionGate(analysis_as_of="2026-11-08")

        record, decision = evaluate_decision(
            "BRK-B", "2026-11-08",
            _state(plan="Entry 556.00, stop 560.00, ATR 9.408. Long."),
            snapshot_id="sec-3",
            equity=100_000.0, risk_budget=1_000.0, max_symbol_exposure=0.05,
        )
        _route_to_broker(record, decision, gate, broker, quantity=8)

        assert decision.action is ExecutionAction.BLOCK
        assert broker.sent == []

    def test_missing_portfolio_sends_zero_orders(self):
        broker = MockPaperBroker()
        gate = ExecutionGate(analysis_as_of="2026-11-08")

        record, decision = evaluate_decision(
            "BRK-B", "2026-11-08",
            _state(plan="Entry 556.00, stop 542.50, ATR 9.408."),
            snapshot_id="sec-4",
            equity=None, risk_budget=1_000.0, max_symbol_exposure=0.05,
        )
        _route_to_broker(record, decision, gate, broker, quantity=8)

        assert decision.action is ExecutionAction.BLOCK
        assert broker.sent == []

    def test_a_direct_bypass_attempt_is_refused(self):
        """Handing a BLOCK decision straight to submit() creates nothing."""
        broker = MockPaperBroker()
        gate = ExecutionGate(analysis_as_of="2026-11-08")
        blocked = GateDecision(ExecutionAction.BLOCK,
                               (GateReason.DATA_QUALITY_BLOCKED,), "BRK-B")
        plan = _plan_for(type("R", (), {"ticker": "BRK-B",
                                        "analysis_as_of": "2026-11-08",
                                        "execution_verdict": None})())
        order, _ = gate.submit(plan, blocked, quantity=8)
        if order is not None:
            broker.send({"order_id": order.order_id})
        assert broker.sent == []
        assert gate.orders() == []

    def test_a_valid_run_can_still_reach_the_paper_broker(self):
        """The chokepoint must be passable, or it proves nothing."""
        broker = MockPaperBroker()
        gate = ExecutionGate(analysis_as_of="2026-11-08")

        # No stale filings, no conflicts, portfolio present, fresh signal.
        # A certified registry is now required for approval (§4), so the valid
        # path supplies one: without a certified metric the gate blocks.
        from tradingagents.dataflows.math.run_registry import (
            RunInputs,
            build_run_registry,
        )

        record, decision = evaluate_decision(
            "BRK-B", "2026-11-08",
            _state(plan="Entry 556.00, stop 542.50, ATR 9.408."),
            snapshot_id="sec-5",
            fundamentals_filings=None,     # check not requested
            equity=100_000.0, cash=100_000.0, risk_budget=1_000.0,
            max_symbol_exposure=0.05,
            trigger_met=True, market_open=True,
            metric_registry=build_run_registry(
                RunInputs(price=556.0, sma200=500.0,
                          book_value_per_share=350.0)),
        )
        _route_to_broker(record, decision, gate, broker, quantity=5)

        # The rating is Overweight + ACCUMULATE_CONDITIONALLY with a met
        # trigger and a sized plan: the gate proposes, and the order flows.
        assert decision.action is ExecutionAction.PROPOSE_PAPER_ORDER
        assert len(broker.sent) == 1
        assert record.execution_verdict.to_dict()["execution_approved"] is True

    def test_the_verdict_reaches_the_audit_json(self, tmp_path):
        from tradingagents.dataflows.gate_integration import write_audit_record

        record, _ = evaluate_decision(
            "BRK-B", "2026-11-08", _state(plan="Entry 556.00, stop 542.50, ATR 9.408."),
            snapshot_id="sec-6", equity=None, risk_budget=1_000.0,
            max_symbol_exposure=0.05,
        )
        path = write_audit_record(record, str(tmp_path))
        data = json.loads(path.read_text(encoding="utf-8"))
        verdict = data["execution"]["verdict"]
        assert verdict["execution_approved"] is False
        assert verdict["authorized_orders"] == []
        assert verdict["blocking_reasons"]
        assert verdict["instrument"] == "BRK-B"


class TestArithmeticReachesTheDecision:
    """P0-B is wired into the decision point, not merely available."""

    def test_a_stated_percentage_contradicting_the_data_blocks(self):
        broker = MockPaperBroker()
        gate = ExecutionGate(analysis_as_of="2026-11-08")

        record, decision = evaluate_decision(
            "BRK-B", "2026-11-08",
            _state(plan="Entry 556.00, stop 542.50, ATR 9.408."),
            snapshot_id="arith-1",
            equity=100_000.0, risk_budget=1_000.0, max_symbol_exposure=0.05,
            price_snapshot={"close": 570.89, "price_as_of": "2026-11-06",
                            "indicator_as_of": "2026-11-06",
                            "indicator": "52w_high"},
            # The report claims -11.3% from the 586.30 high; the truth is -2.63%.
            stated_percentages={
                "distance_from_52w_high": {"stated_pct": -11.3,
                                           "reference": 586.30},
            },
        )
        _route_to_broker(record, decision, gate, broker, quantity=8)

        assert decision.action is ExecutionAction.BLOCK
        assert broker.sent == []
        data = record.to_dict()["data_quality"]
        assert "ARITHMETIC_MISMATCH" in data["blocking_claims"]
        verdicts = data["arithmetic"]
        assert any(v["reason_code"] == "ARITHMETIC_MISMATCH" for v in verdicts)

    def test_a_correct_percentage_does_not_block(self):
        record, decision = evaluate_decision(
            "BRK-B", "2026-11-08",
            _state(plan="Entry 556.00, stop 542.50, ATR 9.408."),
            snapshot_id="arith-2",
            equity=100_000.0, risk_budget=1_000.0, max_symbol_exposure=0.05,
            price_snapshot={"close": 570.89, "price_as_of": "2026-11-06",
                            "indicator_as_of": "2026-11-06",
                            "indicator": "52w_high"},
            stated_percentages={
                "distance_from_52w_high": {"stated_pct": -2.63,
                                           "reference": 586.30},
            },
        )
        data = record.to_dict()["data_quality"]
        assert "ARITHMETIC_MISMATCH" not in (data["blocking_claims"] or [])

    def test_a_price_and_indicator_from_different_sessions_blocks(self):
        record, decision = evaluate_decision(
            "BRK-B", "2026-11-08",
            _state(plan="Entry 556.00, stop 542.50, ATR 9.408."),
            snapshot_id="arith-3",
            equity=100_000.0, risk_budget=1_000.0, max_symbol_exposure=0.05,
            price_snapshot={"close": 570.89, "price_as_of": "2026-11-06",
                            "indicator_as_of": "2026-11-05",
                            "indicator": "SMA200"},
        )
        assert decision.action is ExecutionAction.BLOCK
        data = record.to_dict()["data_quality"]
        assert "PRICE_TIMESTAMP_MISMATCH" in data["blocking_claims"]


class TestVerdictInvariants:
    def test_a_wait_verdict_cannot_carry_orders(self):
        from tradingagents.dataflows.execution_verdict import (
            ExecutionVerdictError,
            build_verdict,
        )

        with pytest.raises(ExecutionVerdictError):
            build_verdict(
                run_id="r", instrument="BRK-B", analysis_as_of="2026-11-08",
                strategic_rating="OVERWEIGHT", execution_action="WAIT",
                blocking_reasons=(), policy_version="p",
                authorized_orders=({"ticker": "BRK-B", "quantity": 8},),
            )

    def test_a_proposal_cannot_carry_blocking_reasons(self):
        from tradingagents.dataflows.execution_verdict import (
            ExecutionVerdictError,
            build_verdict,
        )

        with pytest.raises(ExecutionVerdictError):
            build_verdict(
                run_id="r", instrument="BRK-B", analysis_as_of="2026-11-08",
                strategic_rating="OVERWEIGHT",
                execution_action="PROPOSE_PAPER_ORDER",
                blocking_reasons=("STALE_FUNDAMENTALS",), policy_version="p",
            )

    def test_an_unknown_action_is_refused(self):
        from tradingagents.dataflows.execution_verdict import (
            ExecutionVerdictError,
            build_verdict,
        )

        with pytest.raises(ExecutionVerdictError):
            build_verdict(
                run_id="r", instrument="BRK-B", analysis_as_of="2026-11-08",
                strategic_rating="OVERWEIGHT",
                execution_action="EXECUTE_LIVE", blocking_reasons=(),
                policy_version="p",
            )
