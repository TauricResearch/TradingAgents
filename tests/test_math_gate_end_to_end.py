"""End-to-end proof: wrong LLM numbers reach zero paper orders.

This is the acceptance test the task asks for in §12 ("test che inseriscano
deliberatamente numeri matematicamente errati nell'output simulato di un
LLM") and §11 ("Non è sufficiente chiedere all'LLM di non comprare. Deve
essere il software a bloccare l'esecuzione").

The scenario is the real BRK-B case, played through the real code path:
``evaluate_decision`` → ``evaluate_plan`` → ``ExecutionGate.submit`` → a mock
paper broker. The agents' reports contain the figures the actual 2026-11-08
and 2026-11-09 reports produced — P/B 1.35x, -11.3% from the high, +4.5%
over SMA200, a "2.5 ATR" stop — and the assertion is not that the prose is
corrected but that **nothing is sent to the venue**.

A second test runs the same path with correct figures and asserts one order
does pass, so the blocking is shown to be caused by the errors and not by
the harness refusing everything.
"""

from __future__ import annotations

from decimal import Decimal

from tradingagents.dataflows.execution_gate import (
    ExecutionAction,
    ExecutionGate,
    GateReason,
)
from tradingagents.dataflows.gate_integration import evaluate_decision
from tradingagents.dataflows.math.metric_record import metric
from tradingagents.dataflows.math.registry import MetricRegistry
from tradingagents.dataflows.math.valuation import check_stated_multiple

TICKER = "BRK-B"
TRADE_DATE = "2026-11-08"
BOOK = {"equity": 100_000.0, "cash": 100_000.0, "risk_budget": 1_000.0,
        "max_symbol_exposure": 0.05}


class MockPaperBroker:
    """Records what would have been sent to a paper venue. Sends nothing."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    def send(self, order: dict) -> None:
        self.sent.append(order)


def _state(*, market_report: str = "", plan: str = "",
           fundamentals: str = "") -> dict:
    """A finished run's state, shaped as the graph produces it."""
    return {
        "company_of_interest": TICKER,
        "trade_date": TRADE_DATE,
        "market_report": market_report,
        "sentiment_report": "",
        "news_report": "",
        "fundamentals_report": fundamentals,
        "investment_debate_state": {"bull_history": "", "bear_history": "",
                                    "history": "", "current_response": ""},
        "trader_investment_plan": plan,
        "risk_debate_state": {"aggressive_history": "", "conservative_history": "",
                              "neutral_history": "", "history": ""},
        "investment_plan": "",
        "final_rating": "Overweight",
        "final_trade_decision": "**Rating**: Overweight\nAccumulate on the trigger.",
    }


def _route_to_broker(record, decision, gate: ExecutionGate, broker: MockPaperBroker,
                     quantity: int) -> None:
    """The only path to a venue: the gate must propose, then submit must agree.

    Mirrors any scheduler or API caller. The gate is the single chokepoint, so
    a blocked decision cannot produce a send — which is exactly what the
    tests below verify rather than assume.
    """
    if decision.action is not ExecutionAction.PROPOSE_PAPER_ORDER:
        return
    order, reason = gate.submit(
        plan=_plan_for(decision),
        decision=decision,
        quantity=quantity,
        limit_price=557.0,
    )
    # A duplicate returns the ORIGINAL order with DUPLICATE_ORDER: the caller
    # must check the reason, not only that an order came back, or a retry
    # would send the same simulated order twice.
    if order is not None and reason is not GateReason.DUPLICATE_ORDER:
        broker.send({"ticker": order.ticker, "quantity": order.quantity})


def _plan_for(decision):
    """A gate plan matching the decision, for the submit revalidation."""
    from tradingagents.dataflows.execution_gate import PlanInput
    return PlanInput(
        ticker=decision.ticker,
        rating="OVERWEIGHT",
        intent="ACCUMULATE_CONDITIONALLY",
        trigger_met=True,
        risk_blocked=False,
        market_open=True,
    )


class TestWrongNumbersReachZeroOrders:
    def test_the_pb_135_and_two_point_five_atr_block_the_order(self):
        """The real regression: two wrong multiples, one blocked order."""
        registry = MetricRegistry(run_id="brk-regression")
        # The report's P/B claim, checked against the engine's computation.
        registry.register(check_stated_multiple(
            "price_to_book", "1.35", "570.89", "385.70",
            formula_id="price_div_bvps").record)

        state = _state(
            market_report=("BRK-B is 11.3% below the 52-week high and 4.5% "
                           "above SMA200. P/B of 1.35x."),
            plan="Entry 557.00, stop 547.40, ATR 9.408. The stop sits 2.5 ATR below.",
        )

        record, decision = evaluate_decision(
            TICKER, TRADE_DATE, state,
            snapshot_id="e2e-bad",
            trigger_met=True,
            metric_registry=registry,
            stated_atr_distance=2.5,
            **BOOK,
        )

        broker = MockPaperBroker()
        gate = ExecutionGate(analysis_as_of=TRADE_DATE)
        quantity = record.exposure_sizing.qty if record.exposure_sizing else 0
        _route_to_broker(record, decision, gate, broker, quantity)

        assert decision.action is ExecutionAction.BLOCK
        assert broker.sent == [], "a blocked decision must send nothing"
        codes = {r.value for r in decision.reasons}
        assert "INVALID_STOP_ATR_DISTANCE" in codes
        assert "INVALID_PRICE_TO_BOOK" in codes

    def test_a_wrong_claim_alone_is_enough_to_block(self):
        """No stop problem, only a contradicted percentage: still zero orders."""
        state = _state(
            market_report="The stock trades 4.5% above SMA200.",
            plan="Entry 557.00, stop 547.40, ATR 9.408.",
        )
        registry = MetricRegistry()
        from tradingagents.dataflows.math.claims import (
            ClaimKind,
            NumericClaim,
            check_claim,
        )
        registry.register(check_claim(
            NumericClaim("c1", "distance_from_sma", Decimal("4.5"), "percent",
                         "market", ClaimKind.COMPUTED),
            "14.7003",
        ).record)

        record, decision = evaluate_decision(
            TICKER, TRADE_DATE, state,
            snapshot_id="e2e-claim",
            trigger_met=True,
            metric_registry=registry,
            **BOOK,
        )

        broker = MockPaperBroker()
        gate = ExecutionGate(analysis_as_of=TRADE_DATE)
        quantity = record.exposure_sizing.qty if record.exposure_sizing else 0
        _route_to_broker(record, decision, gate, broker, quantity)

        assert decision.action is ExecutionAction.BLOCK
        assert broker.sent == []

    def test_the_audit_records_what_was_refused(self):
        """§13: the run is reproducible and shows the refusal."""
        registry = MetricRegistry(run_id="brk-audit")
        registry.register(check_stated_multiple(
            "price_to_book", "1.35", "570.89", "385.70",
            formula_id="price_div_bvps").record)

        record, _ = evaluate_decision(
            TICKER, TRADE_DATE,
            _state(market_report="P/B of 1.35x."),
            snapshot_id="e2e-audit", trigger_met=True,
            metric_registry=registry,
            **BOOK,
        )

        assert record.math_verdict is not None
        payload = record.math_verdict.summary()
        assert payload["status"] == "BLOCKED"
        assert "INVALID_PRICE_TO_BOOK" in payload["reasons"]
        # The claim survives in the audit, so the report can state it was wrong.
        metrics = payload["consistency"]["metrics"]
        pb = next(m for m in metrics if m["metric"] == "price_to_book")
        assert pb["llm_claimed_value"] == "1.3500"
        assert pb["value"] == "1.4801"
        assert pb["calculation_status"] == "MISMATCH"


class TestCorrectNumbersPass:
    """The counterpart: sound arithmetic lets the gate propose and send one."""

    def test_consistent_figures_propose_and_send_one_order(self):
        state = _state(
            market_report="The stock trades 14.7% above SMA200.",
            plan="Entry 557.00, stop 547.40, ATR 9.408.",
        )
        # The claim in the report is verifiable only because the engine
        # computed the same metric: an unverifiable claim blocks by design,
        # so a valid path requires the verified value to exist.
        registry = MetricRegistry(run_id="e2e-good")
        registry.register(metric(
            "distance_from_sma", "14.7003", unit="percent",
            formula_id="distance_from_level",
        ))
        record, decision = evaluate_decision(
            TICKER, TRADE_DATE, state,
            snapshot_id="e2e-good",
            trigger_met=True,
            stated_atr_distance=1.02,
            metric_registry=registry,
            **BOOK,
        )

        broker = MockPaperBroker()
        gate = ExecutionGate(analysis_as_of=TRADE_DATE)
        quantity = record.exposure_sizing.qty if record.exposure_sizing else 0
        assert quantity > 0, "the plan should size at least one share"
        _route_to_broker(record, decision, gate, broker, quantity)

        assert decision.action is ExecutionAction.PROPOSE_PAPER_ORDER
        assert len(broker.sent) == 1

    def test_the_same_plan_never_sends_twice(self):
        """Idempotency: a retry cannot duplicate the simulated order."""
        state = _state(plan="Entry 557.00, stop 547.40, ATR 9.408.")
        record, decision = evaluate_decision(
            TICKER, TRADE_DATE, state, snapshot_id="e2e-idem",
            trigger_met=True, stated_atr_distance=1.02, **BOOK,
        )
        broker = MockPaperBroker()
        gate = ExecutionGate(analysis_as_of=TRADE_DATE)
        quantity = record.exposure_sizing.qty if record.exposure_sizing else 1
        _route_to_broker(record, decision, gate, broker, quantity)
        _route_to_broker(record, decision, gate, broker, quantity)
        assert len(broker.sent) == 1
