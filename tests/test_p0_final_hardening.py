"""P0 Final Hardening — regression tests reproducing the 2026-11-08 defects.

Covers the four P0 controls from
``docs/tasks/TRADINGAGENTS_P0_FINAL_HARDENING_COPILOT.md``:

- P0-A filing freshness / canonical facts (FRESH_*)
- P0-B deterministic arithmetic (ARITH_*)
- P0-C multi-tranche risk engine (RISK_*)
- P0-D reconciliation + execution gate (EXEC_*)

The BRK-B numbers are the fixture, never a production rule. All tests are
offline: no network, no LLM, no broker, no SEC credentials.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# P0-A — filing freshness and canonical facts
# ---------------------------------------------------------------------------


class TestP0AFilingFreshness:
    """FRESH_01..06."""

    def _q2(self):
        from tradingagents.dataflows.filing_freshness import FilingRecord
        return FilingRecord("2026-Q2", "2026-06-30", published_date="2026-08-02",
                            filing_date="2026-08-07", form_type="10-Q",
                            accession_number="0001-26-000001")

    def _q3(self):
        from tradingagents.dataflows.filing_freshness import FilingRecord
        return FilingRecord("2026-Q3", "2026-09-30", published_date="2026-11-07",
                            form_type="8-K", accession_number="0001-26-000099")

    def test_fresh_01_q2_used_while_q3_published_is_stale(self):
        from tradingagents.dataflows.filing_freshness import check_filing_freshness

        verdict = check_filing_freshness(
            "2026-06-30", [self._q2(), self._q3()], "2026-11-08",
            used_period="2026-Q2",
        )
        assert verdict.status == "STALE_FUNDAMENTALS"
        assert verdict.blocks_decision
        # The Q3 filing is named with its accession for the audit trail.
        assert verdict.latest_filing.accession_number == "0001-26-000099"

    def test_fresh_02_no_lookahead_before_publication(self):
        """The day before the Q3 release, Q2 was the freshest known."""
        from tradingagents.dataflows.filing_freshness import check_filing_freshness

        verdict = check_filing_freshness(
            "2026-06-30", [self._q2(), self._q3()], "2026-11-06",
        )
        assert not verdict.blocks_decision

    def test_fresh_03_unreachable_sec_blocks_order_dependent_on_freshness(self):
        from tradingagents.dataflows.filing_freshness import check_filing_freshness

        verdict = check_filing_freshness("2026-06-30", [], "2026-11-08")
        assert verdict.status == "FUNDAMENTALS_UNAVAILABLE"
        assert verdict.blocks_decision

    def test_fresh_04_share_classes_reconcile_within_one_period(self):
        """Class-A book value converted to class-B before P/B, same period."""
        from tradingagents.dataflows.valuation import EquityInputs, reconcile_valuation

        # Equity 761,368 over 1,303.907 equivalent B shares -> BVPS ~583.91.
        # The reported per-A figure is that times the 1500:1 ratio.
        converted = reconcile_valuation(EquityInputs(
            price=570.89, price_class="B", price_currency="USD",
            equity=761_368.0, equity_currency="USD",
            shares_outstanding=1_303.907,
            bvps_reported=875_866.0, bvps_class="A", bvps_currency="USD",
            share_class_ratio=1500,
        ))
        assert converted.is_usable
        assert converted.book_value_per_share == pytest.approx(583.91, abs=0.02)
        assert converted.price_to_book == pytest.approx(0.9777, abs=1e-3)
        # Single-class instrument: no conversion, straightforward ratio.
        single = reconcile_valuation(EquityInputs(
            price=270.0, price_class=None, price_currency="USD",
            equity=100_000.0, equity_currency="USD",
            shares_outstanding=100.0,
            bvps_reported=None, bvps_class=None, bvps_currency=None,
            share_class_ratio=None,
        ))
        assert single.price_to_book == pytest.approx(0.27)

    def test_fresh_05_adjusted_eps_vs_gaap_filing_is_a_definition_mismatch(self):
        from tradingagents.dataflows.fact_registry import AgentFact, register_facts

        report = register_facts([
            AgentFact(fact_key="eps", metric_id="eps_gaap", agent="fundamentals",
                      value=5.94, unit="USD", period="2026-Q3",
                      metric_definition="eps_gaap_diluted", verified=True,
                      source_type="sec_filing"),
            AgentFact(fact_key="eps", metric_id="eps_adjusted", agent="news",
                      value=6.10, unit="USD", period="2026-Q3",
                      metric_definition="eps_adjusted", verified=False,
                      source_type="news_article"),
        ])
        assert report.blocks_decision
        assert any(c.reason_code == "METRIC_DEFINITION_MISMATCH"
                   for c in report.conflicts)

    def test_fresh_06_non_december_fiscal_year_uses_the_fiscal_period(self):
        """A September fiscal year end (AAPL-style) is identified correctly."""
        from tradingagents.dataflows.filing_freshness import (
            FilingRecord,
            latest_known_filing,
        )

        fy24 = FilingRecord("2024-FY", "2024-09-28", filing_date="2024-11-01")
        q1_25 = FilingRecord("2025-Q1", "2024-12-28", filing_date="2025-01-31")
        assert latest_known_filing([fy24, q1_25], "2025-02-10") is q1_25
        # And an unknown period is not silently treated as the latest.
        assert latest_known_filing([fy24, q1_25], "2024-12-01") is fy24


# ---------------------------------------------------------------------------
# P0-B — deterministic arithmetic
# ---------------------------------------------------------------------------


class TestP0BArithmetic:
    """ARITH_01..06."""

    def test_arith_01_distance_from_52w_high(self):
        from tradingagents.dataflows.arithmetic import percent_distance

        assert percent_distance(570.89, 586.30) == pytest.approx(-2.6285, abs=1e-3)
        # The report's -11.3% is not what this data supports.
        assert percent_distance(570.89, 586.30) != pytest.approx(-11.3, abs=0.1)

    def test_arith_02_distance_from_sma200(self):
        from tradingagents.dataflows.arithmetic import percent_distance

        assert percent_distance(570.89, 497.723) == pytest.approx(14.7005, abs=1e-3)

    def test_arith_03_distance_from_sma50(self):
        from tradingagents.dataflows.arithmetic import percent_distance

        assert percent_distance(570.89, 521.560) == pytest.approx(9.4587, abs=1e-3)

    def test_arith_04_distance_from_52w_low(self):
        from tradingagents.dataflows.arithmetic import percent_distance

        assert percent_distance(570.89, 464.01) == pytest.approx(23.0340, abs=1e-3)

    def test_arith_05_stated_percentage_contradicting_the_data_is_rejected(self):
        from tradingagents.dataflows.arithmetic import check_stated_percentage

        mismatch = check_stated_percentage(
            stated_pct=-11.3, reference=586.30, current=570.89,
            label="distance from 52w high",
        )
        assert mismatch.reason_code == "ARITHMETIC_MISMATCH"
        assert mismatch.blocks_decision

        ok = check_stated_percentage(
            stated_pct=-2.63, reference=586.30, current=570.89,
            label="distance from 52w high",
        )
        assert not ok.blocks_decision

    def test_arith_06_intraday_and_close_to_close_are_distinct(self):
        """Open→close is not the same metric as close→close."""
        from tradingagents.dataflows.arithmetic import (
            close_to_close_return,
            open_to_close_return,
        )

        o2c = open_to_close_return(584.23, 572.33)
        c2c = close_to_close_return(579.09, 572.33)
        assert o2c == pytest.approx(-2.0370, abs=1e-3)
        assert c2c == pytest.approx(-1.1673, abs=1e-3)
        assert o2c != pytest.approx(c2c, abs=0.5)

    def test_arith_multi_currency_percentages_are_dimensionless(self):
        """The same formula applies to a EUR quote — no per-ticker rule."""
        from tradingagents.dataflows.arithmetic import percent_distance

        assert percent_distance(14.20, 15.00) == pytest.approx(-5.3333, abs=1e-3)

    def test_arith_zero_and_none_are_not_computed(self):
        from tradingagents.dataflows.arithmetic import percent_distance

        assert percent_distance(570.89, 0.0) is None
        assert percent_distance(None, 586.30) is None
        assert percent_distance(570.89, None) is None

    def test_arith_price_timestamp_mismatch_is_reported(self):
        from tradingagents.dataflows.arithmetic import check_price_timestamp_alignment

        verdict = check_price_timestamp_alignment(
            price_as_of="2026-11-06", indicator_as_of="2026-11-05",
            indicator="SMA200",
        )
        assert verdict.reason_code == "PRICE_TIMESTAMP_MISMATCH"
        assert verdict.blocks_decision  # an indicator from another session

        aligned = check_price_timestamp_alignment(
            price_as_of="2026-11-06", indicator_as_of="2026-11-06",
            indicator="SMA200",
        )
        assert not aligned.blocks_decision


# ---------------------------------------------------------------------------
# P0-C — multi-tranche risk engine
# ---------------------------------------------------------------------------


class TestP0CMultiTrancheRisk:
    """RISK_01..08."""

    def test_risk_01_leg_a_risk_per_share_and_atr(self):
        from tradingagents.dataflows.risk_engine import tranche_risk

        leg = tranche_risk(entry=556.0, stop=542.50, atr=9.408, direction="LONG")
        assert leg.risk_per_share == pytest.approx(13.50)
        assert leg.atr_multiple == pytest.approx(1.435, abs=1e-3)
        assert leg.valid

    def test_risk_02_leg_b_has_its_own_risk_not_leg_a(self):
        from tradingagents.dataflows.risk_engine import tranche_risk

        leg = tranche_risk(entry=543.50, stop=542.50, atr=9.408, direction="LONG")
        assert leg.risk_per_share == pytest.approx(1.0)
        assert leg.atr_multiple == pytest.approx(0.1063, abs=1e-3)
        # A stop-distance this tight is flagged, not silently accepted.
        assert leg.reason_code == "STOP_TOO_TIGHT_FOR_POLICY"

    def test_risk_03_exposure_cap_reduces_the_stop_based_size(self):
        """126 shares (≈70.6k) must not pass a 5% per-symbol cap."""
        from tradingagents.dataflows.risk_engine import size_with_exposure_cap

        uncapped = size_with_exposure_cap(
            entry=560.0, stop=552.07, atr=9.408, risk_budget=1_000.0,
            equity=100_000.0, max_symbol_exposure=None,
        )
        assert uncapped.qty > 100

        capped = size_with_exposure_cap(
            entry=560.0, stop=552.07, atr=9.408, risk_budget=1_000.0,
            equity=100_000.0, max_symbol_exposure=0.05,
        )
        assert capped.qty == 8
        assert capped.notional == pytest.approx(4_480.0)
        assert capped.binding_constraint == "EXPOSURE_CAP"

    def test_risk_04_aggregate_risk_counts_open_orders_and_positions(self):
        from tradingagents.dataflows.risk_engine import aggregate_tranche_risk

        result = aggregate_tranche_risk(
            [
                {"entry": 556.0, "stop": 542.50, "atr": 9.408},
                {"entry": 543.50, "stop": 542.50, "atr": 9.408},
            ],
            risk_budget=1_000.0, equity=100_000.0,
            max_symbol_exposure=0.05,
            existing_notional=2_000.0, existing_risk=100.0,
        )
        # The existing position's risk and notional are part of the total.
        assert result.total_risk >= 100.0
        assert result.total_notional >= 2_000.0
        assert result.total_notional <= 5_000.0 + 1e-9

    def test_risk_05_stop_on_the_wrong_side_is_invalid(self):
        from tradingagents.dataflows.risk_engine import tranche_risk

        long_bad = tranche_risk(entry=556.0, stop=560.0, atr=9.408,
                                direction="LONG")
        assert not long_bad.valid
        assert long_bad.reason_code == "INVALID_STOP_SIDE"

        short_bad = tranche_risk(entry=556.0, stop=550.0, atr=9.408,
                                 direction="SHORT")
        assert not short_bad.valid
        assert short_bad.reason_code == "INVALID_STOP_SIDE"

    def test_risk_06_gap_beyond_the_stop_widens_the_loss(self):
        from tradingagents.dataflows.risk_engine import stress_exit

        stressed = stress_exit(entry=556.0, stop=542.50, atr=9.408,
                               gap_atr=1.0, slippage_pct=0.001)
        assert stressed.stressed_exit < stressed.stop
        assert stressed.extra_loss_per_share > 9.0   # a full ATR of gap

    def test_risk_07_missing_portfolio_and_duplicates_fail_closed(self):
        from tradingagents.dataflows.risk_engine import size_with_exposure_cap

        no_portfolio = size_with_exposure_cap(
            entry=560.0, stop=552.07, atr=9.408, risk_budget=1_000.0,
            equity=None, max_symbol_exposure=0.05,
        )
        assert no_portfolio.qty == 0
        assert "PORTFOLIO_CONTEXT_MISSING" in [r.value for r in no_portfolio.reasons]

        too_small = size_with_exposure_cap(
            entry=560.0, stop=552.07, atr=9.408, risk_budget=1_000.0,
            equity=100_000.0, max_symbol_exposure=0.05, cash=500.0,
        )
        assert too_small.qty == 0
        assert "CASH_EXCEEDED" in [r.value for r in too_small.reasons]

    def test_risk_08_alternative_scenarios_stay_independent_orders(self):
        """A pullback leg and a breakout leg keep their own entry, stop and
        trigger; they are never merged into one order with a shared stop."""
        from tradingagents.dataflows.risk_engine import aggregate_tranche_risk

        result = aggregate_tranche_risk(
            [
                {"entry": 556.0, "stop": 542.50, "atr": 9.408,
                 "strategy_id": "pullback", "trigger": "limit_556"},
                {"entry": 586.0, "stop": 570.00, "atr": 9.408,
                 "strategy_id": "breakout", "trigger": "close_above_586"},
            ],
            risk_budget=2_000.0, equity=100_000.0,
            max_symbol_exposure=0.10,
        )
        assert len(result.tranches) == 2
        # Each leg was priced on its own stop distance.
        assert result.tranches[0].risk != result.tranches[1].risk


# ---------------------------------------------------------------------------
# P0-D — decision reconciliation and execution gate
# ---------------------------------------------------------------------------


class TestP0DReconciliationAndGate:
    """EXEC_01..09."""

    def _plan(self, **overrides):
        from tradingagents.dataflows.execution_gate import PlanInput

        kwargs = {
            "ticker": "BRK-B", "rating": "OVERWEIGHT",
            "intent": "ACCUMULATE_CONDITIONALLY", "trigger_met": True,
            "risk_blocked": False, "risk_reasons": (),
            "data_quality_blocked": False, "post_event_status": "OBSERVABLE",
            "signal_as_of": "2026-11-09", "analysis_as_of": "2026-11-09",
            "market_open": True,
        }
        kwargs.update(overrides)
        return PlanInput(**kwargs)

    def test_exec_01_trader_target_is_invalidated_by_the_pm_decision(self):
        from tradingagents.dataflows.order_reconciliation import (
            OrderCandidate,
            reconcile_order,
        )

        trader = OrderCandidate(stage="trader", ticker="BRK-B", side="LONG",
                                quantity=125, entry=556.0, stop=542.50)
        pm = OrderCandidate(stage="portfolio_manager", ticker="BRK-B",
                            side="LONG", quantity=105, entry=556.0, stop=542.50)
        result = reconcile_order(trader, pm, prior_authorized=True)
        assert result.final.quantity == 105
        assert result.pm_prevailed
        assert result.requires_revalidation
        assert not result.authorized   # the revision voided the authorization

    def test_exec_02_unpriced_event_leaves_the_plan_waiting(self):
        from tradingagents.dataflows.execution_gate import evaluate_plan

        decision = evaluate_plan(self._plan(
            post_event_status="NOT_YET_OBSERVABLE", trigger_met=False,
            market_open=False, signal_as_of="2026-11-08",
            analysis_as_of="2026-11-08",
        ))
        assert decision.action.value == "WAIT"
        assert not decision.creates_order

    def test_exec_03_unmet_conditional_trigger_orders_nothing(self):
        from tradingagents.dataflows.execution_gate import evaluate_plan

        decision = evaluate_plan(self._plan(trigger_met=False))
        assert decision.action.value == "WAIT"
        assert not decision.creates_order

    def test_exec_04_no_portfolio_means_no_order_whatever_the_rating(self):
        from tradingagents.dataflows.execution_gate import evaluate_plan
        from tradingagents.dataflows.risk_engine import RiskReason

        decision = evaluate_plan(self._plan(
            risk_blocked=True,
            risk_reasons=(RiskReason.PORTFOLIO_CONTEXT_MISSING,),
        ))
        assert decision.action.value == "BLOCK"
        assert not decision.creates_order

    def test_exec_05_the_paper_adapter_cannot_be_reached_without_approval(self):
        """Even calling submit() directly with a blocked plan creates nothing."""
        from tradingagents.dataflows.execution_gate import (
            ExecutionGate,
            evaluate_plan,
        )

        gate = ExecutionGate(analysis_as_of="2026-11-09")
        plan = self._plan(data_quality_blocked=True)
        blocked = evaluate_plan(plan)
        order, reason = gate.submit(plan, blocked, quantity=8)
        assert order is None
        assert gate.orders() == []

    def test_exec_06_changing_stop_after_approval_forces_revalidation(self):
        from tradingagents.dataflows.order_reconciliation import (
            OrderCandidate,
            reconcile_order,
        )

        trader = OrderCandidate(stage="trader", ticker="BRK-B", side="LONG",
                                quantity=8, entry=556.0, stop=542.50)
        pm = OrderCandidate(stage="portfolio_manager", ticker="BRK-B",
                            side="LONG", quantity=8, entry=556.0, stop=548.00)
        result = reconcile_order(trader, pm, prior_authorized=True)
        assert result.requires_revalidation
        assert not result.authorized

    def test_exec_07_overweight_and_buy_never_imply_approval(self):
        from tradingagents.dataflows.execution_gate import evaluate_plan

        # OVERWEIGHT + MAINTAIN (a HOLD posture) does not create an order.
        hold = evaluate_plan(self._plan(intent="MAINTAIN"))
        assert not hold.creates_order
        # And no rating value sets an "approved" flag by itself.
        assert not hasattr(hold, "execution_approved")

    def test_exec_08_mock_broker_receives_zero_orders_on_any_failure(self):
        from tradingagents.dataflows.execution_gate import ExecutionGate

        class MockBroker:
            def __init__(self):
                self.orders = []

            def send(self, order):
                self.orders.append(order)

        broker = MockBroker()
        gate = ExecutionGate(analysis_as_of="2026-11-09")
        for failure in (
            {"data_quality_blocked": True},
            {"risk_blocked": True},
            {"trigger_met": False},
            {"market_open": False},
            {"signal_as_of": "2026-11-01"},
        ):
            plan = self._plan(**failure)
            from tradingagents.dataflows.execution_gate import evaluate_plan
            decision = evaluate_plan(plan)
            order, _ = gate.submit(plan, decision, quantity=8)
            if order is not None:
                broker.send(order)

        assert broker.orders == []

    def test_exec_09_a_fully_valid_plan_can_be_approved_once(self):
        """The gate must be able to pass: otherwise it is useless."""
        from tradingagents.dataflows.execution_gate import (
            ExecutionGate,
            evaluate_plan,
        )

        gate = ExecutionGate(analysis_as_of="2026-11-09")
        plan = self._plan()
        decision = evaluate_plan(plan)
        assert decision.action.value == "PROPOSE_PAPER_ORDER"

        first, reason = gate.submit(plan, decision, quantity=8)
        assert first is not None
        assert reason.value == "OK"
        # A retry is idempotent: no second order.
        second, again = gate.submit(plan, decision, quantity=8)
        assert second is first
        assert again.value == "DUPLICATE_ORDER"
        assert len(gate.orders()) == 1

    def test_exec_structured_verdict_is_machine_readable(self, tmp_path):
        from tradingagents.dataflows.execution_verdict import build_verdict

        verdict = build_verdict(
            run_id="fixture-001", instrument="BRK-B",
            analysis_as_of="2026-11-08", strategic_rating="OVERWEIGHT",
            execution_action="WAIT",
            blocking_reasons=("STALE_FUNDAMENTALS",
                              "PORTFOLIO_CONTEXT_MISSING",
                              "EVENT_PRICE_NOT_OBSERVABLE"),
            policy_version="test-policy",
        )
        data = verdict.to_dict()
        assert data["execution_approved"] is False
        assert data["authorized_orders"] == []
        assert data["blocking_reasons"] == [
            "STALE_FUNDAMENTALS", "PORTFOLIO_CONTEXT_MISSING",
            "EVENT_PRICE_NOT_OBSERVABLE",
        ]
        assert data["instrument"] == "BRK-B"
        assert data["run_id"] == "fixture-001"
        # An approved verdict is the only one carrying orders.
        approved = build_verdict(
            run_id="r", instrument="AAPL", analysis_as_of="2026-11-08",
            strategic_rating="OVERWEIGHT", execution_action="PROPOSE_PAPER_ORDER",
            blocking_reasons=(), policy_version="p",
            authorized_orders=({"ticker": "AAPL", "quantity": 8},),
        )
        assert approved.to_dict()["execution_approved"] is True
        assert approved.to_dict()["authorized_orders"] == [
            {"ticker": "AAPL", "quantity": 8}
        ]


# ---------------------------------------------------------------------------
# Multi-ticker generalisation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ticker,currency,entry,stop,atr", [
    ("BRK-B", "USD", 556.0, 542.50, 9.408),
    ("AAPL", "USD", 270.0, 264.0, 4.0),
    ("NVDA", "USD", 180.0, 175.0, 3.0),
    ("ENI.MI", "EUR", 14.20, 13.80, 0.30),
])
def test_p0_controls_are_ticker_agnostic(ticker, currency, entry, stop, atr):
    from tradingagents.dataflows.risk_engine import tranche_risk

    leg = tranche_risk(entry=entry, stop=stop, atr=atr, direction="LONG")
    assert leg.valid
    assert leg.risk_per_share == pytest.approx(entry - stop)
    assert leg.atr_multiple == pytest.approx((entry - stop) / atr)
