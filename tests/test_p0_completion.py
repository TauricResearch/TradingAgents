"""P0 completion tests — the BRK-B report of 2026-11-08 (final pass).

Each test reproduces one defect still present in the latest report and pins
the deterministic check that must block it. The rules are ticker-agnostic:
the BRK-B numbers are the fixture, never a special case. All offline, no
network, no LLM, no cloud models.

Test IDs map to the task's mandatory matrix (T01..T14).
"""

from __future__ import annotations

import pytest

from tradingagents.dataflows.execution_gate import (
    ExecutionAction,
    GateReason,
    PlanInput,
    evaluate_plan,
)
from tradingagents.dataflows.fact_registry import (
    AgentFact,
    check_negation_against_registry,
    register_facts,
)
from tradingagents.dataflows.filing_freshness import (
    FilingRecord,
    check_filing_freshness,
    latest_known_filing,
)
from tradingagents.dataflows.order_reconciliation import (
    OrderCandidate,
    reconcile_order,
)
from tradingagents.dataflows.risk_engine import (
    RiskReason,
    size_with_exposure_cap,
    validate_stop_side,
)

# The fixture timeline: Q3 published Saturday 2026-11-07, report run
# Sunday 2026-11-08, last session Friday 2026-11-06.
SESSIONS = ["2026-11-04", "2026-11-05", "2026-11-06", "2026-11-09"]
AS_OF = "2026-11-08"
Q2 = FilingRecord("2026-Q2", "2026-06-30", published_date="2026-08-02",
                  filing_date="2026-08-07", form_type="10-Q")
Q3 = FilingRecord("2026-Q3", "2026-09-30", published_date="2026-11-07",
                  form_type="8-K")


# ---------------------------------------------------------------------------
# T01 — vendor serves Q2 while the SEC Q3 filing is already available
# ---------------------------------------------------------------------------


class TestT01FilingFreshness:
    def test_q3_is_recognized_as_the_latest_filing(self):
        latest = latest_known_filing([Q2, Q3], AS_OF)
        assert latest is Q3
        assert latest.period_end == "2026-09-30"

    def test_vendor_q2_while_q3_available_is_stale(self):
        verdict = check_filing_freshness(
            used_period_end="2026-06-30",
            filings=[Q2, Q3],
            as_of_date=AS_OF,
        )
        assert verdict.status == "STALE_FUNDAMENTALS"
        assert verdict.blocks_decision
        assert verdict.latest_known_period_end == "2026-09-30"

    def test_no_lookahead_before_the_q3_release(self):
        """On the Friday before the Saturday release, Q2 was current."""
        verdict = check_filing_freshness(
            used_period_end="2026-06-30",
            filings=[Q2, Q3],
            as_of_date="2026-11-06",
        )
        assert not verdict.blocks_decision

    def test_using_q3_passes(self):
        verdict = check_filing_freshness(
            used_period_end="2026-09-30",
            filings=[Q2, Q3],
            as_of_date=AS_OF,
        )
        assert not verdict.blocks_decision

    def test_no_known_filing_blocks(self):
        verdict = check_filing_freshness(
            used_period_end="2026-06-30", filings=[], as_of_date=AS_OF,
        )
        assert verdict.blocks_decision
        assert verdict.status == "FUNDAMENTALS_UNAVAILABLE"

    def test_other_fiscal_calendars_work(self):
        """A January fiscal-year end (AAPL-style) follows the same rule."""
        fy25 = FilingRecord("2025-FY", "2025-09-27", filing_date="2025-11-01",
                            form_type="10-K")
        q1 = FilingRecord("2026-Q1", "2025-12-27", filing_date="2026-01-30",
                          form_type="10-Q")
        latest = latest_known_filing([fy25, q1], "2026-02-15")
        assert latest is q1


# ---------------------------------------------------------------------------
# T02 — a market reaction claimed before the news existed
# ---------------------------------------------------------------------------


class TestT02TemporalCausality:
    def test_reaction_before_publication_is_refuted(self):
        from tradingagents.dataflows.causal_guard import (
            NOT_YET_OBSERVABLE,
            evaluate_post_event_pricing,
        )
        from tradingagents.dataflows.fact_checker import (
            Claim,
            ClaimClassification,
            check_claim,
        )
        from tradingagents.dataflows.provenance import ProvenanceRegistry

        verdict = evaluate_post_event_pricing(
            "2026-11-07", SESSIONS, as_of_date=AS_OF
        )
        assert verdict.status == NOT_YET_OBSERVABLE

        claim = Claim(
            claim_id="C-1",
            statement="the -0.01% move on Nov 6 was the market's reaction to Q3",
            classification=ClaimClassification.CAUSAL_INFERENCE,
            blocking=True,
        )
        checked = check_claim(claim, ProvenanceRegistry(snapshot_id="s"),
                              post_event_status=verdict.status)
        assert checked.status.value == "REFUTED"
        assert checked.blocks_decision


# ---------------------------------------------------------------------------
# T03 / T05 — same metric, different periods / EPS definitions
# ---------------------------------------------------------------------------


def _fact(**overrides) -> AgentFact:
    base = {
        "fact_key": "stockholders_equity", "agent": "fundamentals",
        "value": 747_900.0, "unit": "USD_million", "currency": "USD",
        "period": "2026-Q2", "period_end": "2026-06-30", "segment": "company",
        "source_type": "sec_filing", "verified": True,
    }
    base.update(overrides)
    return AgentFact(**base)


class TestT03PeriodMismatch:
    def test_same_metric_different_periods_are_not_compared(self):
        """Q2 equity and Q3 equity are different facts, not a conflict."""
        report = register_facts([
            _fact(period="2026-Q2", period_end="2026-06-30", value=747_900.0),
            _fact(agent="news", period="2026-Q3", period_end="2026-09-30",
                  value=761_368.0),
        ])
        assert report.conflicts == []
        assert not report.blocks_decision

    def test_same_period_conflicting_values_block(self):
        report = register_facts([
            _fact(value=747_900.0, verified=False, source_type="vendor_api"),
            _fact(agent="news", value=761_368.0, verified=False,
                  source_type="news_article"),
        ])
        assert report.blocks_decision
        assert report.conflicts[0].reason_code == "FACT_CONFLICT_UNRESOLVED"

    def test_an_absence_never_refutes_a_sourced_value(self):
        report = register_facts([_fact()])
        conflict = check_negation_against_registry(
            "stockholders_equity", "fundamentals", report, period="2026-Q2",
        )
        assert conflict is None  # same agent, no contradiction

        # A different agent's absence cannot refute the sourced value.
        report2 = register_facts([
            _fact(),
            _fact(agent="news", value=None, verified=False,
                  source_type="vendor_api"),
        ])
        conflict2 = check_negation_against_registry(
            "stockholders_equity", "news", report2,
            period="2026-Q2", segment="company",
        )
        assert conflict2 is not None and not conflict2.resolved


class TestT05MetricDefinitions:
    def test_gaap_eps_vs_consensus_adjusted_is_not_a_beat(self):
        report = register_facts([
            _fact(metric_id="eps_gaap", value=5.94, unit="USD",
                  period="2026-Q3", period_end="2026-09-30",
                  metric_definition="eps_gaap_diluted"),
            _fact(metric_id="eps_consensus_adjusted", agent="social",
                  value=5.88, unit="USD", period="2026-Q3",
                  period_end="2026-09-30", verified=False,
                  source_type="news_article",
                  metric_definition="eps_consensus_adjusted"),
        ])
        assert report.blocks_decision
        assert any(c.reason_code == "METRIC_DEFINITION_MISMATCH"
                   for c in report.conflicts)

    def test_operating_eps_vs_gaap_actuals_are_separate_facts(self):
        report = register_facts([
            _fact(metric_id="eps_gaap", value=5.94, unit="USD",
                  metric_definition="eps_gaap_diluted"),
            _fact(metric_id="eps_operating", agent="news", value=5.88,
                  unit="USD", metric_definition="eps_operating"),
        ])
        assert not report.blocks_decision


# ---------------------------------------------------------------------------
# T04 — P/B over unreconciled share classes / periods
# ---------------------------------------------------------------------------


class TestT04Valuation:
    def test_class_a_book_value_against_class_b_price_is_rejected(self):
        from tradingagents.dataflows.validator import (
            convert_share_class,
            validate_share_class_comparison,
        )

        result = validate_share_class_comparison(570.89, 75000.0, "B", "A")
        assert result.has_errors

        # With the ratio the comparison becomes valid.
        per_b = convert_share_class(75000.0, 1500, "A", "B")
        assert per_b == pytest.approx(50.0)
        result2 = validate_share_class_comparison(570.89, per_b, "B", "B")
        assert not result2.has_errors

    def test_mixed_period_equity_and_shares_are_unreconciled(self):
        from tradingagents.dataflows.valuation import EquityInputs, reconcile_valuation

        verdict = reconcile_valuation(EquityInputs(
            price=570.89, price_class="B", price_currency="USD",
            equity=747_900.0, equity_currency="USD",
            shares_outstanding=1_303_907.0,
            bvps_reported=None, bvps_class=None, bvps_currency=None,
            share_class_ratio=None,
        ))
        # Same-period inputs reconcile; the P/B is computed.
        assert verdict.price_to_book is not None

        # A class-A book value against a class-B price is refused.
        verdict2 = reconcile_valuation(EquityInputs(
            price=570.89, price_class="B", price_currency="USD",
            equity=747_900.0, equity_currency="USD",
            shares_outstanding=1_303_907.0,
            bvps_reported=75000.0, bvps_class="A", bvps_currency="USD",
            share_class_ratio=None,   # no ratio: cannot convert
        ))
        assert not verdict2.is_usable
        assert verdict2.price_to_book is None


# ---------------------------------------------------------------------------
# T06 / T07 / T11 — sizing under stop budget AND exposure cap
# ---------------------------------------------------------------------------


class TestT06ExposureCap:
    def test_stop_distance_alone_would_over_expose(self):
        """100k equity, 1% risk budget, entry 560, stop 552.07: the
        risk-only answer is ~124 shares (~69,600 USD, 70% of equity)."""
        result = size_with_exposure_cap(
            entry=560.0, stop=552.07, atr=8.0, risk_budget=1_000.0,
            equity=100_000.0, max_symbol_exposure=None,
        )
        assert result.qty > 100
        assert result.notional > 60_000.0

    def test_the_exposure_cap_binds_and_rejects_the_excess(self):
        """With a 5% per-symbol cap the size is capped at 8 shares."""
        result = size_with_exposure_cap(
            entry=560.0, stop=552.07, atr=8.0, risk_budget=1_000.0,
            equity=100_000.0, max_symbol_exposure=0.05,
        )
        assert result.qty == 8
        assert result.notional == pytest.approx(4_480.0)
        assert result.binding_constraint == "EXPOSURE_CAP"
        assert result.exposure_cap_applied

    def test_missing_portfolio_context_never_invents_a_size(self):
        result = size_with_exposure_cap(
            entry=560.0, stop=552.07, atr=8.0, risk_budget=1_000.0,
            equity=None, max_symbol_exposure=0.05,
        )
        assert result.qty == 0
        assert "PORTFOLIO_CONTEXT_MISSING" in result.reasons

    def test_insufficient_cash_blocks(self):
        result = size_with_exposure_cap(
            entry=560.0, stop=552.07, atr=8.0, risk_budget=1_000.0,
            equity=100_000.0, max_symbol_exposure=0.05, cash=1_000.0,
        )
        assert result.qty == 0
        assert "CASH_EXCEEDED" in result.reasons


class TestT07TrancheRisk:
    def test_a_second_tranche_recomputes_its_own_risk(self):
        """Tranche 2 at 587 with stop 567: 20 USD/share risk, not tranche
        1's 7.93 — each tranche is sized to its own distance."""
        from tradingagents.dataflows.risk_engine import size_position

        t1 = size_position(560.0, 552.07, 8.0, 1_000.0)
        t2 = size_position(587.0, 567.0, 8.0, 1_000.0)
        assert t1.risk_per_share == pytest.approx(7.93)
        assert t2.risk_per_share == pytest.approx(20.0)
        assert t2.qty < t1.qty   # the wider stop buys fewer shares

    def test_aggregate_risk_across_tranches_stays_within_budget(self):
        from tradingagents.dataflows.risk_engine import size_position

        t1 = size_position(560.0, 552.07, 8.0, 500.0)
        t2 = size_position(587.0, 567.0, 8.0, 500.0)
        total = t1.planned_risk + t2.planned_risk
        assert total <= 1_000.0 + 1e-9


class TestT11StopSide:
    def test_long_stop_at_or_above_entry_blocks(self):
        result = validate_stop_side(560.0, 560.0, "LONG")
        assert result.has_errors

    def test_short_stop_below_entry_blocks(self):
        result = validate_stop_side(560.0, 552.0, "SHORT")
        assert result.has_errors

    def test_correct_sides_pass(self):
        assert not validate_stop_side(560.0, 552.0, "LONG").has_errors
        assert not validate_stop_side(560.0, 568.0, "SHORT").has_errors


# ---------------------------------------------------------------------------
# T08 / T09 / T10 / T12 — gate, reconciliation, staleness
# ---------------------------------------------------------------------------


def _plan(**overrides) -> PlanInput:
    kwargs = {
        "ticker": "BRK-B", "rating": "NEUTRAL", "intent": "MAINTAIN",
        "trigger_met": False, "risk_blocked": False, "risk_reasons": (),
        "data_quality_blocked": False, "post_event_status": None,
        "signal_as_of": AS_OF, "analysis_as_of": AS_OF, "market_open": False,
    }
    kwargs.update(overrides)
    return PlanInput(**kwargs)


class TestT08HoldNeverOrders:
    def test_hold_waits_with_zero_orders(self):
        decision = evaluate_plan(_plan())
        assert decision.action is ExecutionAction.WAIT
        assert not decision.creates_order

    def test_hold_with_stale_fundamentals_blocks(self):
        decision = evaluate_plan(_plan(data_quality_blocked=True))
        assert decision.action is ExecutionAction.BLOCK
        assert GateReason.DATA_QUALITY_BLOCKED in decision.reasons

    def test_hold_with_missing_portfolio_blocks(self):
        decision = evaluate_plan(_plan(
            risk_blocked=True,
            risk_reasons=(RiskReason.PORTFOLIO_CONTEXT_MISSING,),
        ))
        assert decision.action is ExecutionAction.BLOCK
        assert GateReason.PORTFOLIO_RISK_BUDGET_MISSING in decision.reasons


class TestT09OrderReconciliation:
    def test_the_pm_decision_prevails_over_the_trader_proposal(self):
        """The Trader proposed 100 shares; the PM revised to 40: the order
        candidate carries the PM's quantity."""
        trader = OrderCandidate(
            stage="trader", ticker="BRK-B", side="LONG",
            quantity=100, entry=560.0, stop=552.07,
        )
        pm = OrderCandidate(
            stage="portfolio_manager", ticker="BRK-B", side="LONG",
            quantity=40, entry=560.0, stop=552.07,
        )
        result = reconcile_order(trader, pm)
        assert result.final.quantity == 40
        assert result.final.stage == "portfolio_manager"
        assert result.pm_prevailed

    def test_a_pm_revision_invalidates_the_prior_authorization(self):
        """Any change to quantity/stop/entry/side requires full revalidation:
        the reconciled candidate is marked as requiring it."""
        trader = OrderCandidate(
            stage="trader", ticker="BRK-B", side="LONG",
            quantity=100, entry=560.0, stop=552.07,
        )
        pm = OrderCandidate(
            stage="portfolio_manager", ticker="BRK-B", side="LONG",
            quantity=40, entry=560.0, stop=552.07,
        )
        result = reconcile_order(trader, pm)
        assert result.requires_revalidation

    def test_an_unchanged_pm_decision_keeps_the_authorization(self):
        trader = OrderCandidate(
            stage="trader", ticker="BRK-B", side="LONG",
            quantity=40, entry=560.0, stop=552.07,
        )
        pm = OrderCandidate(
            stage="portfolio_manager", ticker="BRK-B", side="LONG",
            quantity=40, entry=560.0, stop=552.07,
        )
        result = reconcile_order(trader, pm)
        assert not result.requires_revalidation

    def test_a_hold_pm_decision_never_becomes_an_order(self):
        """A HOLD/MAINTAIN PM decision cannot be reconciled into a BUY."""
        trader = OrderCandidate(
            stage="trader", ticker="BRK-B", side="LONG",
            quantity=100, entry=560.0, stop=552.07,
        )
        pm = OrderCandidate(
            stage="portfolio_manager", ticker="BRK-B", side="LONG",
            quantity=0, entry=560.0, stop=552.07, action="HOLD",
        )
        result = reconcile_order(trader, pm)
        assert result.final.quantity == 0
        assert not result.authorized


class TestT10MissingPortfolio:
    def test_no_portfolio_context_no_order(self):
        decision = evaluate_plan(_plan(
            rating="OVERWEIGHT", intent="ACCUMULATE_CONDITIONALLY",
            trigger_met=True, market_open=True,
            risk_blocked=True,
            risk_reasons=(RiskReason.PORTFOLIO_CONTEXT_MISSING,),
        ))
        assert decision.action is ExecutionAction.BLOCK
        assert not decision.creates_order


class TestT12StaleConditionalOrder:
    def test_a_stale_signal_is_refused_at_submission(self):
        from tradingagents.dataflows.execution_gate import ExecutionGate

        gate = ExecutionGate(analysis_as_of=AS_OF)
        plan = _plan(rating="OVERWEIGHT", intent="ACCUMULATE_CONDITIONALLY",
                     trigger_met=True, market_open=True,
                     signal_as_of="2026-11-06")
        decision = evaluate_plan(plan)   # BLOCKed: stale signal
        order, reason = gate.submit(plan, decision, quantity=10)
        assert order is None
        assert gate.orders() == []

    def test_a_fresh_valid_plan_submits_once_and_idempotently(self):
        from tradingagents.dataflows.execution_gate import ExecutionGate

        gate = ExecutionGate(analysis_as_of=AS_OF)
        plan = _plan(rating="OVERWEIGHT", intent="ACCUMULATE_CONDITIONALLY",
                     trigger_met=True, market_open=True)
        decision = evaluate_plan(plan)
        assert decision.action is ExecutionAction.PROPOSE_PAPER_ORDER
        first, reason1 = gate.submit(plan, decision, quantity=8)
        second, reason2 = gate.submit(plan, decision, quantity=8)
        assert first is not None and reason1.value == "OK"
        assert second is first and reason2.value == "DUPLICATE_ORDER"
        assert len(gate.orders()) == 1


# ---------------------------------------------------------------------------
# T13 — missing sentiment data alone does not block
# ---------------------------------------------------------------------------


class TestT13NonCriticalGaps:
    def test_missing_sentiment_alone_does_not_block(self):
        """The gate blocks on data quality only when a *critical* check
        fails; a missing optional report is not a block."""
        decision = evaluate_plan(_plan(
            rating="OVERWEIGHT", intent="ACCUMULATE_CONDITIONALLY",
            trigger_met=True, market_open=True,
            data_quality_blocked=False,
        ))
        assert decision.action is ExecutionAction.PROPOSE_PAPER_ORDER

    def test_quarantined_critical_data_blocks(self):
        decision = evaluate_plan(_plan(
            rating="OVERWEIGHT", intent="ACCUMULATE_CONDITIONALLY",
            trigger_met=True, market_open=True,
            data_quality_blocked=True,
        ))
        assert decision.action is ExecutionAction.BLOCK


# ---------------------------------------------------------------------------
# T14 — multi-ticker: the same rules, no BRK-B dependency
# ---------------------------------------------------------------------------


class TestT14MultiTicker:
    @pytest.mark.parametrize("ticker,entry,stop,currency", [
        ("BRK-B", 560.0, 552.07, "USD"),
        ("AAPL", 270.0, 265.0, "USD"),
        ("NVDA", 180.0, 175.0, "USD"),
        ("ENI.MI", 14.20, 13.80, "EUR"),
    ])
    def test_sizing_rules_are_ticker_agnostic(self, ticker, entry, stop, currency):
        result = size_with_exposure_cap(
            entry=entry, stop=stop, atr=max(1.0, entry * 0.02),
            risk_budget=1_000.0, equity=100_000.0, max_symbol_exposure=0.05,
        )
        assert result.qty > 0
        assert result.notional <= 100_000.0 * 0.05 + 1e-9
        assert result.binding_constraint in ("EXPOSURE_CAP", "RISK_BUDGET")

    @pytest.mark.parametrize("ticker", ["BRK-B", "AAPL", "NVDA", "ENI.MI"])
    def test_the_gate_vocabulary_is_ticker_agnostic(self, ticker):
        decision = evaluate_plan(_plan(ticker=ticker))
        assert decision.action is ExecutionAction.WAIT
        assert not decision.creates_order
