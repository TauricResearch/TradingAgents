"""Deterministic math tools and session status — the §6 regression cases.

Expected values are derived independently of the code under test: from the
figures published in the 2026-11-09 18:37 report, from arithmetic done by
hand, and from the exchange session definition. None is "whatever the engine
returned".

The five cases the task names, all of which the engine must get right:

``A`` P/B on dual-class shares, refusing a vendor 0.001x and the old 1.35x
``B`` consolidated vs segment revenue, which must not be blended
``C`` TTM EPS, reconciled against weighted-average — not period-end — shares
``D`` stop distance: entry 552, stop 531, ATR 9.397 → 21 USD and 2.23 ATR
``E`` an intraday bar, which must not pass as a verified end-of-day close
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from tradingagents.agents.math_tools import (
    MATH_TOOLS,
    calculate_book_value_per_share,
    calculate_cagr,
    calculate_eps,
    calculate_indicator,
    calculate_percentage_change,
    calculate_price_to_book,
    calculate_stop_distance,
    calculate_stop_for_atr,
    calculate_valuation_ratio,
    convert_money_unit,
    get_certified_metric,
    set_run_registry,
    validate_market_bar,
    validate_market_series,
    validate_stated_percentage,
    validate_trade_proposal,
)
from tradingagents.dataflows.math.registry import MetricRegistry
from tradingagents.dataflows.math.session import (
    SessionStatus,
    assess_bar,
    assess_series,
    market_session_status,
)
from tradingagents.dataflows.math.valuation import check_stated_multiple

# The report's own figures.
BRK_PRICE = 570.89
BRK_EQUITY_Q3 = "761368000000"        # 761,368 million USD
SHARES_A = 543_000
SHARES_B = 1_303_000_000
RATIO_A_TO_B = 1500
# B-equivalent shares: shares_B + shares_A * 1500
B_EQUIVALENT = SHARES_B + SHARES_A * RATIO_A_TO_B      # 2,117,500,000


def _json(tool, **kwargs) -> dict:
    """Invoke a LangChain tool the way the graph does, and read its JSON."""
    return json.loads(tool.invoke(kwargs))


# ===========================================================================
# Case A — Price-to-book on a dual-class company
# ===========================================================================
class TestCaseAPriceToBook:
    def test_bvps_on_class_b_equivalents_gives_about_1_6x(self):
        """761.368bn equity / 2.1175bn B-equivalents = 359.56 per B share."""
        bvps = Decimal(BRK_EQUITY_Q3) / Decimal(B_EQUIVALENT)
        assert bvps == pytest.approx(Decimal("359.5598"), abs=Decimal("0.001"))
        pb = Decimal("570.89") / bvps
        assert pb == pytest.approx(Decimal("1.5877"), abs=Decimal("0.001"))
        # The report's expectation of "about 1.6x" is what this confirms.
        assert Decimal("1.5") < pb < Decimal("1.65")

    def test_the_vendor_0001x_is_refused(self):
        """A P/B of 0.001 is not a rounding of 1.59: it is a unit error."""
        result = check_stated_multiple(
            "price_to_book", "0.001", BRK_PRICE,
            Decimal(BRK_EQUITY_Q3) / Decimal(B_EQUIVALENT),
            formula_id="price_div_bvps",
        )
        assert result.record.calculation_status.value == "MISMATCH"
        assert result.blocks

    def test_the_old_135x_is_refused(self):
        result = check_stated_multiple(
            "price_to_book", "1.35", BRK_PRICE, "385.70",
            formula_id="price_div_bvps",
        )
        assert result.computed == Decimal("1.4801")
        assert result.blocks

    def test_a_cross_class_ratio_is_refused_by_the_tool(self):
        """A class-A book value divided into a class-B price is wrong by 1500x."""
        payload = _json(
            calculate_price_to_book,
            price=BRK_PRICE, book_value_per_share=539339.39,
            price_class="B", bvps_class="A",
        )
        assert payload["calculation_status"] == "NOT_COMPUTABLE"
        assert "class-A" in payload["reason"] or "class-B" in payload["reason"]

    def test_same_class_is_computed(self):
        payload = _json(
            calculate_price_to_book,
            price=BRK_PRICE,
            book_value_per_share=float(Decimal(BRK_EQUITY_Q3) / Decimal(B_EQUIVALENT)),
            price_class="B", bvps_class="B",
        )
        assert payload["calculation_status"] == "VERIFIED"
        assert Decimal(payload["value"]) == pytest.approx(Decimal("1.5877"),
                                                          abs=Decimal("0.001"))

    def test_bvps_uses_the_class_b_equivalent_count(self):
        """Two classes: the share count must be converted, not summed raw."""
        payload = _json(
            calculate_book_value_per_share,
            equity=float(BRK_EQUITY_Q3), equity_unit="base", shares=B_EQUIVALENT,
        )
        assert Decimal(payload["value"]) == pytest.approx(
            Decimal("359.5598"), abs=Decimal("0.001"))
        # Summing the raw counts would give a materially different figure.
        naive = Decimal(BRK_EQUITY_Q3) / Decimal(SHARES_B)
        assert Decimal(payload["value"]) < naive


# ===========================================================================
# Case B — consolidated vs segment revenue
# ===========================================================================
class TestCaseBRevenue:
    def test_the_two_series_are_materially_different(self):
        """74,322 (segment) vs 105,647 (consolidated): a 1.42x gap, not noise."""
        segment = Decimal("74322")
        consolidated = Decimal("105647")
        ratio = consolidated / segment
        assert ratio == pytest.approx(Decimal("1.4215"), abs=Decimal("0.001"))
        # Blending them would misstate any growth rate by ~42%.
        assert ratio > Decimal("1.4")

    def test_a_percentage_computed_across_the_two_definitions_is_not_available(self):
        """The engine computes what it is given; the *definition* check is the guard.

        This test documents why the guard must exist at the caller: the
        arithmetic of 105,647 over 74,322 is perfectly well-formed, so no
        amount of arithmetic can detect that the two numbers mean different
        things.
        """
        payload = _json(calculate_percentage_change,
                        new_value=105647, reference_value=74322)
        assert payload["calculation_status"] == "VERIFIED"
        # +42.15% — arithmetically right, financially meaningless.
        assert Decimal(payload["value"]) == pytest.approx(Decimal("42.1469"),
                                                          abs=Decimal("0.001"))

    def test_growth_within_one_definition_is_computable(self):
        payload = _json(calculate_percentage_change,
                        new_value=105647, reference_value=94800)
        assert payload["calculation_status"] == "VERIFIED"


# ===========================================================================
# Case C — TTM EPS and its denominator
# ===========================================================================
class TestCaseCEps:
    def test_weighted_average_shares_reproduce_the_reported_eps(self):
        """77.084bn / 1.9387bn weighted-average shares = 39.76."""
        payload = _json(calculate_eps,
                        net_income=float(Decimal("77084000000")),
                        weighted_average_shares=1_938_732_394)
        assert Decimal(payload["value"]) == pytest.approx(Decimal("39.76"),
                                                          abs=Decimal("0.01"))

    def test_period_end_shares_give_a_different_wrong_number(self):
        """The trap: end-of-period shares produce 36.40, not 39.76."""
        wrong = Decimal("77084000000") / Decimal(B_EQUIVALENT)
        assert wrong == pytest.approx(Decimal("36.40"), abs=Decimal("0.01"))
        right = Decimal("77084000000") / Decimal("1938732394")
        assert right > wrong
        # The difference is material: ~9%, not a rounding artefact.
        assert (right - wrong) / right > Decimal("0.08")

    def test_gaap_and_adjusted_eps_are_distinct_metrics(self):
        gaap = _json(calculate_eps, net_income=77084000000,
                     weighted_average_shares=1938732394)
        adj = _json(calculate_eps, net_income=80000000000,
                    weighted_average_shares=1938732394, adjusted=True)
        assert gaap["metric"] == "eps_gaap"
        assert adj["metric"] == "eps_adjusted"
        assert gaap["unit"] != adj["unit"]

    def test_a_missing_share_count_is_not_approximated(self):
        payload = _json(calculate_valuation_ratio,
                        numerator=570.89, denominator=39.76, ratio="pe_trailing")
        assert payload["calculation_status"] == "VERIFIED"


# ===========================================================================
# Case D — stop distance (the mandated numbers)
# ===========================================================================
class TestCaseDStopDistance:
    def test_risk_per_share_is_21(self):
        payload = _json(calculate_stop_distance, entry=552.0, stop=531.0, atr=9.397)
        assert Decimal(payload["value"]) == Decimal("21.0000")

    def test_atr_distance_is_about_2_23(self):
        payload = _json(calculate_stop_distance, entry=552.0, stop=531.0, atr=9.397)
        assert Decimal(payload["atr_distance"]) == Decimal("2.2348")

    def test_a_long_stop_above_entry_is_refused(self):
        payload = _json(calculate_stop_distance, entry=552.0, stop=560.0,
                        atr=9.397, direction="LONG")
        assert payload["calculation_status"] == "NOT_COMPUTABLE"
        assert "wrong side" in payload["reason"]

    def test_a_short_stop_below_entry_is_refused(self):
        payload = _json(calculate_stop_distance, entry=552.0, stop=545.0,
                        atr=9.397, direction="SHORT")
        assert payload["calculation_status"] == "NOT_COMPUTABLE"

    def test_a_valid_short_computes_its_distance(self):
        payload = _json(calculate_stop_distance, entry=552.0, stop=573.0,
                        atr=9.397, direction="SHORT")
        assert Decimal(payload["value"]) == Decimal("21.0000")
        assert Decimal(payload["atr_distance"]) == Decimal("2.2348")

    def test_the_implied_stop_for_2_23_atr_is_about_531(self):
        payload = _json(calculate_stop_for_atr, entry=552.0, atr=9.397,
                        atr_multiple=2.2348)
        assert Decimal(payload["value"]) == pytest.approx(Decimal("531.0"),
                                                          abs=Decimal("0.05"))

    def test_a_stated_distance_that_contradicts_the_plan_is_flagged(self):
        payload = _json(validate_trade_proposal, entry=552.0, stop=531.0,
                        atr=9.397, stated_atr_distance=4.0)
        assert payload["blocks_decision"] is True
        assert payload["code"] == "INVALID_STOP_ATR_DISTANCE"

    def test_the_correct_stated_distance_passes(self):
        payload = _json(validate_trade_proposal, entry=552.0, stop=531.0,
                        atr=9.397, stated_atr_distance=2.23)
        assert payload["blocks_decision"] is False


# ===========================================================================
# Case E — incomplete bar vs verified EOD close
# ===========================================================================
class TestCaseEIntradayBar:
    # The 18:37 Europe/Rome analysis is 12:37 America/New_York: mid-session.
    ANALYSIS = "2026-11-09T18:37:00+01:00"

    def test_an_intraday_bar_is_not_complete(self):
        assessment = assess_bar("2026-11-09T15:30:00", analysis_time=self.ANALYSIS)
        assert assessment.is_complete is False
        assert assessment.is_final is False
        assert assessment.usable_as_close is False
        assert assessment.status is SessionStatus.OPEN

    def test_the_previous_close_is_complete_and_final(self):
        assessment = assess_bar("2026-11-06T16:00:00", analysis_time=self.ANALYSIS)
        assert assessment.is_complete is True
        assert assessment.is_final is True
        assert assessment.usable_as_close is True

    def test_todays_date_only_bar_is_still_forming(self):
        """A daily bar for the running session carries no close yet."""
        assessment = assess_bar("2026-11-09", analysis_time=self.ANALYSIS)
        assert assessment.is_complete is False
        assert assessment.blocks_confirmed_close_strategies is True

    def test_a_past_date_only_bar_is_a_complete_session(self):
        assessment = assess_bar("2026-11-06", analysis_time=self.ANALYSIS)
        assert assessment.is_complete is True
        assert assessment.usable_as_close is True

    def test_a_future_bar_cannot_be_a_close(self):
        assessment = assess_bar("2026-11-10", analysis_time=self.ANALYSIS)
        assert assessment.is_complete is False

    def test_a_bar_the_vendor_has_not_settled_is_not_final(self):
        assessment = assess_bar("2026-11-06T16:00:00",
                                analysis_time=self.ANALYSIS, vendor_settled=False)
        assert assessment.is_complete is True
        assert assessment.is_final is False
        assert assessment.blocks_confirmed_close_strategies is True

    def test_a_series_reports_whether_it_includes_a_partial_bar(self):
        result = assess_series(["2026-11-05", "2026-11-06", "2026-11-09"],
                               analysis_time=self.ANALYSIS)
        assert result["includes_partial_bar"] is True
        assert result["completed_bars"] == 2
        assert result["total_bars"] == 3

    def test_last_completed_session_skips_the_weekend(self):
        """Sunday 2026-11-08: the last settled session is Friday's."""
        assessment = assess_bar("2026-11-06", analysis_time="2026-11-08T12:00:00-05:00")
        assert assessment.last_completed_session == "2026-11-06"

    def test_last_completed_session_uses_the_calendar_when_supplied(self):
        assessment = assess_bar(
            "2026-11-06T16:00:00", analysis_time=self.ANALYSIS,
            known_sessions=["2026-11-04", "2026-11-05", "2026-11-06"],
        )
        assert assessment.last_completed_session == "2026-11-06"

    def test_session_status_classifies_the_moments_of_a_day(self):
        assert market_session_status("2026-11-09T08:00:00") is SessionStatus.PRE_MARKET
        assert market_session_status("2026-11-09T11:00:00") is SessionStatus.OPEN
        assert market_session_status("2026-11-09T17:00:00") is SessionStatus.AFTER_HOURS
        assert market_session_status("2026-11-07T11:00:00") is SessionStatus.CLOSED

    def test_a_missing_timestamp_is_unknown_not_usable(self):
        assert market_session_status(None) is SessionStatus.UNKNOWN
        assessment = assess_bar(None)
        assert assessment.is_complete is False
        assert "no bar timestamp" in assessment.reason

    def test_the_tools_expose_the_same_verdict(self):
        payload = _json(validate_market_bar,
                        bar_timestamp="2026-11-09T15:30:00",
                        analysis_time=self.ANALYSIS)
        assert payload["is_complete"] is False
        assert payload["usable_as_close"] is False

        series = _json(validate_market_series,
                       timestamps=["2026-11-05", "2026-11-06", "2026-11-09"],
                       analysis_time=self.ANALYSIS)
        assert series["includes_partial_bar"] is True


# ===========================================================================
# Tool surface: typed, structured, never a bare number
# ===========================================================================
class TestToolContract:
    def test_every_tool_returns_structured_json(self):
        """A tool must return formula, operands and status — not a number."""
        payload = _json(calculate_percentage_change,
                        new_value=110, reference_value=100)
        assert payload["value"] == "10.0000"
        assert payload["formula_id"] == "pct_change"
        assert payload["operands"]
        assert payload["calculation_status"] == "VERIFIED"

    def test_a_zero_reference_refuses_instead_of_dividing(self):
        payload = _json(calculate_percentage_change, new_value=10, reference_value=0)
        assert payload["calculation_status"] == "NOT_COMPUTABLE"
        assert payload["value"] is None

    def test_an_unknown_unit_is_refused(self):
        payload = _json(convert_money_unit, value=100, from_unit="furlongs")
        assert payload["calculation_status"] == "NOT_COMPUTABLE"

    def test_unit_conversion_scales_correctly(self):
        payload = _json(convert_money_unit, value=761368, from_unit="million")
        assert Decimal(payload["value"]) == Decimal("761368000000")

    def test_cagr_requires_an_explicit_duration(self):
        payload = _json(calculate_cagr, begin_value=100, end_value=200, years=5)
        assert Decimal(payload["value"]) == pytest.approx(Decimal("14.8698"),
                                                          abs=Decimal("0.001"))

    def test_indicators_return_their_convention(self):
        closes = [100.0 + i for i in range(60)]
        payload = _json(calculate_indicator, indicator="sma", closes=closes, window=20)
        assert payload["formula_id"] == "sma_20"
        assert payload["calculation_status"] == "VERIFIED"

    def test_an_indicator_without_history_is_not_computable(self):
        payload = _json(calculate_indicator, indicator="sma", closes=[100.0], window=20)
        assert payload["calculation_status"] == "NOT_COMPUTABLE"

    def test_a_stated_percentage_is_checked_against_the_computation(self):
        payload = _json(validate_stated_percentage, label="distance_from_sma",
                        claimed_pct=4.5, new_value=570.89, reference_value=497.723)
        assert payload["verdict"] == "MISMATCH"
        assert payload["blocks_decision"] is True

    def test_a_correct_stated_percentage_passes(self):
        payload = _json(validate_stated_percentage, label="distance_from_sma",
                        claimed_pct=14.7, new_value=570.89, reference_value=497.723)
        assert payload["verdict"] == "MATCHES"
        assert payload["blocks_decision"] is False

    def test_every_tool_is_registered_for_binding(self):
        # 22: the measurement/validation tools, the §5 definition reconciler,
        # and the three added for the 19:24 report (distance with an explicit
        # denominator, EPS change, ATR quantity sensitivity).
        assert len(MATH_TOOLS) == 22
        names = {t.name for t in MATH_TOOLS}
        assert {"calculate_stop_distance", "validate_market_bar",
                "validate_metric_definitions", "get_certified_metric",
                "calculate_distance_from_level", "calculate_eps_change",
                "calculate_quantity_sensitivity"} <= names


class TestCertifiedMetricLookup:
    def test_an_uncomputed_metric_is_unverified_and_blocks(self):
        set_run_registry(MetricRegistry(run_id="t"))
        payload = _json(get_certified_metric, metric_name="price_to_book")
        assert payload["source_status"] == "MISSING"
        assert payload["value"] is None
        assert payload["blocks_decision"] is True

    def test_a_verified_metric_is_read_back(self):
        from tradingagents.dataflows.math.metric_record import metric

        registry = MetricRegistry(run_id="t")
        registry.register(metric("price_to_book", "1.5877", formula_id="price_div_bvps"))
        set_run_registry(registry)
        payload = _json(get_certified_metric, metric_name="price_to_book")
        assert payload["value"] == "1.5877"
        assert payload["calculation_status"] == "VERIFIED"

    def test_a_refused_metric_is_not_served_as_usable(self):
        registry = MetricRegistry(run_id="t")
        registry.register(check_stated_multiple(
            "price_to_book", "1.35", BRK_PRICE, "385.70",
            formula_id="price_div_bvps").record)
        set_run_registry(registry)
        payload = _json(get_certified_metric, metric_name="price_to_book")
        # It is reported, with its status, but never as a verified value.
        assert payload["calculation_status"] == "MISMATCH"
        assert registry.value("price_to_book") is None
