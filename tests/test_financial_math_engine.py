"""Financial Math Engine — the mandatory §12 test matrix.

Every expected value in this file is derived independently: a hand
calculation, a published definition, or an identity that must hold whatever
the implementation does. None is "whatever the engine returned", because a
test that reads its expectation from the code under test proves only that
the code is consistent with itself.

The regression cases carry the numbers from the two BRK-B reports (2026-11-08
and 2026-11-09), which is where the defects these modules exist to catch were
first observed:

- a P/B of 1.35x where 570.89 / 385.70 = 1.4801,
- a "2.5 ATR" stop where entry 557.00, stop 547.40 and ATR 9.408 give 1.02,
- a "-11.3% from the high" where 570.89 vs 586.30 gives -2.63%,
- a "+4.5% over SMA200" where 570.89 vs 497.723 gives +14.70%.

The last section proves the Execution Gate refuses to create an order when
those figures are present, and the paper broker receives nothing.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from tradingagents.dataflows.execution_gate import (
    ExecutionAction,
    GateReason,
    PlanInput,
    evaluate_plan,
)
from tradingagents.dataflows.math.claims import (
    ClaimKind,
    ClaimVerdict,
    NumericClaim,
    accept_non_fact,
    check_claim,
    check_reports,
    extract_claims,
)
from tradingagents.dataflows.math.consistency import (
    check_report_consistency,
    check_stop_consistency,
)
from tradingagents.dataflows.math.math_gate import evaluate_math
from tradingagents.dataflows.math.metric_record import (
    CalculationStatus,
    SourceStatus,
    metric,
)
from tradingagents.dataflows.math.precision import (
    Money,
    Unit,
    as_decimal,
    cagr,
    convert_unit,
    divide,
    pct_change,
    percentage_points,
    quantize,
    safe_ratio,
)
from tradingagents.dataflows.math.registry import MetricRegistry
from tradingagents.dataflows.math.technical import (
    atr_distance,
    average_true_range,
    bollinger_bands,
    distance_from_level,
    exponential_moving_average,
    macd,
    simple_moving_average,
    standard_deviation,
    stop_for_atr_multiple,
    volume_weighted_moving_average,
)
from tradingagents.dataflows.math.valuation import (
    book_value_per_share,
    check_stated_multiple,
    dual_class_book_value_per_share,
    earnings_per_share,
    price_to_book,
    price_to_earnings,
)

# --- BRK-B regression constants (from the two reports under test) ----------
BRK_PRICE = "570.89"
BRK_BVPS_CLAIMED = "385.70"
BRK_PB_CLAIMED = "1.35"
BRK_HIGH = "586.30"
BRK_SMA50 = "521.560"
BRK_SMA200 = "497.723"
BRK_ENTRY = "557.00"
BRK_STOP = "547.40"
BRK_ATR = "9.408"


# ===========================================================================
# 1. Percentage changes, positive and negative
# ===========================================================================
class Test01PercentageChanges:
    """§6: the single convention ``(new/reference - 1) * 100``."""

    def test_positive_change(self):
        # 110 from 100 is +10%: trivial by hand.
        assert pct_change(110, 100) == Decimal("10.0000")

    def test_negative_change(self):
        assert pct_change(90, 100) == Decimal("-10.0000")

    def test_zero_change(self):
        assert pct_change(100, 100) == Decimal("0.0000")

    def test_brk_distance_from_high(self):
        # 570.89 / 586.30 - 1 = -0.026283... -> -2.6283%
        assert pct_change(BRK_PRICE, BRK_HIGH) == Decimal("-2.6283")

    def test_brk_distance_from_sma50(self):
        # 570.89 / 521.560 - 1 = +0.094582... -> +9.4582%
        assert pct_change(BRK_PRICE, BRK_SMA50) == Decimal("9.4582")

    def test_brk_distance_from_sma200(self):
        # 570.89 / 497.723 - 1 = +0.147003... -> +14.7003%
        assert pct_change(BRK_PRICE, BRK_SMA200) == Decimal("14.7003")

    def test_percentage_points_are_not_relative_change(self):
        """4.5% -> 5.0% is +0.5 points but +11.1% relative: both exist."""
        assert percentage_points(Decimal("0.5")) == Decimal("0.5000")
        assert pct_change("5.0", "4.5") == Decimal("11.1111")


# ===========================================================================
# 2. Precision and rounding
# ===========================================================================
class Test02Precision:
    """§3: Decimal, explicit rounding, no float drift."""

    def test_float_enters_through_its_shortest_repr(self):
        """A float must not smuggle in binary noise."""
        assert as_decimal(570.89) == Decimal("570.89")
        # Decimal(float) would give 570.8900000000000436...
        assert str(as_decimal(570.89)) == "570.89"

    def test_decimal_addition_is_exact(self):
        """0.1 + 0.2 == 0.3 exactly, which float cannot do."""
        assert as_decimal("0.1") + as_decimal("0.2") == Decimal("0.3")

    def test_rounding_is_half_up(self):
        # ROUND_HALF_UP: 0.125 -> 0.13, not banker's 0.12.
        assert quantize(Decimal("0.125"), Decimal("0.01")) == Decimal("0.13")

    def test_no_intermediate_rounding(self):
        """A chain stays exact: the value is quantized once, at the end.

        Decimal division at the default 28-digit precision cannot reproduce
        1/3 exactly, so the assertion is that the *engine* does not round
        early — the raw quotient is not truncated to the output quantum
        before being used again.
        """
        third = divide(1, 3)
        assert third is not None
        # The intermediate keeps full precision, not a 4-decimal rounding.
        assert len(str(third).split(".")[1]) > 4

    def test_non_finite_is_refused(self):
        assert as_decimal(float("nan")) is None
        assert as_decimal(float("inf")) is None
        assert as_decimal("not-a-number") is None

    def test_bool_is_not_a_number(self):
        assert as_decimal(True) is None

    def test_comma_thousands_separator_is_read(self):
        assert as_decimal("1,222,000") == Decimal("1222000")


# ===========================================================================
# 3. Null or invalid denominators
# ===========================================================================
class Test03InvalidDenominators:
    def test_divide_by_zero_is_none_not_an_exception(self):
        assert divide(10, 0) is None

    def test_divide_by_missing_is_none(self):
        assert divide(10, None) is None
        assert divide(None, 10) is None

    def test_ratio_with_zero_denominator_is_none(self):
        assert safe_ratio(570.89, 0) is None

    def test_pct_change_against_zero_is_none(self):
        assert pct_change(10, 0) is None

    def test_zero_reference_is_not_a_percentage(self):
        assert distance_from_level(100, 0) is None


# ===========================================================================
# 4. USD / million / billion conversions
# ===========================================================================
class Test04UnitConversions:
    def test_millions_to_base(self):
        # 761,368 million is 761,368,000,000
        assert convert_unit(761368, Unit.MILLION, Unit.BASE) == Decimal("761368000000")

    def test_base_to_billions(self):
        assert convert_unit("1220000000000", Unit.BASE, Unit.BILLION) == Decimal("1220")

    def test_thousands_to_millions(self):
        # 1,500,000 thousand is 1,500 million: the factor is 1000, not 1e6.
        assert convert_unit(1500000, Unit.THOUSAND, Unit.MILLION) == Decimal("1500")

    def test_round_trip_is_identity(self):
        start = Decimal("761368")
        there = convert_unit(start, Unit.MILLION, Unit.BASE)
        back = convert_unit(there, Unit.BASE, Unit.MILLION)
        assert back == start

    def test_unknown_unit_is_refused(self):
        assert convert_unit(100, "furlongs", Unit.BASE) is None

    def test_vendor_unit_labels_are_understood(self):
        assert Unit.parse("USD_million") is Unit.MILLION
        assert Unit.parse("in millions") is Unit.MILLION
        assert Unit.parse("bn") is Unit.BILLION
        assert Unit.parse("thousands") is Unit.THOUSAND

    def test_money_carries_its_currency_and_unit(self):
        money = Money(761368, "usd", Unit.MILLION)
        assert money.to_base() == Decimal("761368000000")
        assert money.to(Unit.BILLION).amount == Decimal("761.368")


# ===========================================================================
# 5. Incompatible units
# ===========================================================================
class Test05IncompatibleUnits:
    def test_different_currencies_are_incompatible(self):
        assert not Money(100, "USD").compatible(Money(100, "EUR"))

    def test_unlabelled_currency_is_not_compatible(self):
        """Unknown is not 'the same as'."""
        assert not Money(100).compatible(Money(100, "USD"))

    def test_same_currency_different_scale_is_compatible(self):
        assert Money(1, "USD", Unit.MILLION).compatible(Money(1, "USD", Unit.BASE))

    def test_equality_requires_same_currency_and_amount(self):
        assert Money(1, "USD", Unit.MILLION) == Money(1000000, "USD", Unit.BASE)

    def test_bvps_from_millions_matches_hand_calculation(self):
        """Equity in millions must be converted before dividing by shares."""
        # 761,368,000,000 / 1,438,000,000 = 529.4631... per share
        record = book_value_per_share(761368, 1_438_000_000,
                                      equity_unit=Unit.MILLION)
        assert record.value is not None
        assert record.value == pytest.approx(Decimal("529.4631"), abs=Decimal("0.001"))


# ===========================================================================
# 6. CAGR over different periods
# ===========================================================================
class Test06Cagr:
    def test_ten_percent_over_one_year(self):
        assert cagr(100, 110, 1) == Decimal("10.0000")

    def test_doubling_over_five_years(self):
        # 2 ** (1/5) - 1 = 14.8698%
        assert cagr(100, 200, 5) == Decimal("14.8698")

    def test_same_growth_over_longer_span_is_a_lower_rate(self):
        short = cagr(100, 200, 5)
        long = cagr(100, 200, 10)
        assert long < short
        # 2 ** (1/10) - 1 = 7.1773%
        assert long == Decimal("7.1773")

    def test_zero_duration_is_none(self):
        assert cagr(100, 200, 0) is None

    def test_non_positive_endpoint_is_none(self):
        assert cagr(0, 200, 5) is None
        assert cagr(-100, 200, 5) is None

    def test_decline_is_negative(self):
        # 0.5 ** 0.2 - 1 = -12.9449%
        assert cagr(200, 100, 5) == Decimal("-12.9449")


# ===========================================================================
# 7. Market cap and book value
# ===========================================================================
class Test07MarketCapAndBookValue:
    def test_market_cap_is_price_times_shares(self):
        from tradingagents.dataflows.math.valuation import market_cap
        # 570.89 * 2,155,000,000 = 1,230,266,950,000
        record = market_cap("570.89", 2_155_000_000, currency="USD")
        assert record.value == Decimal("1230266950000.00") or \
            record.value == pytest.approx(Decimal("1230266950000"))

    def test_bvps_from_equity_and_shares(self):
        # 761,368,000,000 / 1,438,000,000 = 529.4631...
        record = book_value_per_share("761368000000", 1_438_000_000)
        assert record.value == pytest.approx(Decimal("529.4631"), abs=Decimal("0.001"))

    def test_missing_shares_yields_not_computable(self):
        record = book_value_per_share("761368000000", None)
        assert record.calculation_status is CalculationStatus.NOT_COMPUTABLE
        assert record.value is None

    def test_metric_record_carries_formula_and_operands(self):
        record = book_value_per_share("761368000000", 1_438_000_000,
                                      period_end="2026-09-30")
        summary = record.summary()
        assert summary["formula_id"] == "equity_div_shares"
        assert summary["period_end"] == "2026-09-30"
        assert "equity" in summary["operands"]


# ===========================================================================
# 8. Share classes A/B
# ===========================================================================
class Test08ShareClasses:
    def test_class_b_equivalents_use_the_1500_ratio(self):
        """1 A = 1500 B, so B_equivalent = shares_B + shares_A * 1500."""
        # 543,000 A shares + 1,303,000,000 B shares
        # B_equivalent = 1,303,000,000 + 543,000*1500 = 2,117,500,000
        record = dual_class_book_value_per_share(
            "761368000000", 543_000, 1_303_000_000, period_end="2026-09-30")
        expected = Decimal("761368000000") / Decimal("2117500000")
        assert record.value == pytest.approx(expected, abs=Decimal("0.0001"))

    def test_the_equivalent_count_is_recorded_as_an_operand(self):
        record = dual_class_book_value_per_share("761368000000", 543_000, 1_303_000_000)
        assert record.operands["class_b_equivalent"] == "2117500000"

    def test_a_missing_ratio_refuses_rather_than_assuming_1500(self):
        record = dual_class_book_value_per_share(
            "761368000000", 543_000, 1_303_000_000, class_a_to_b_ratio=None)
        assert record.value is None
        assert record.calculation_status is CalculationStatus.NOT_COMPUTABLE

    def test_a_ratio_of_one_is_not_a_dual_class_conversion(self):
        """A single-class issuer passes no ratio, so no scaling happens."""
        record = dual_class_book_value_per_share(
            "1000000", 0, 1000, class_a_to_b_ratio=1)
        assert record.value == Decimal("1000")

    def test_ignoring_the_ratio_would_be_wrong_by_a_large_factor(self):
        """Proof the conversion matters: dividing by raw shares errs."""
        naive = Decimal("761368000000") / Decimal("1303543000")
        correct = dual_class_book_value_per_share(
            "761368000000", 543_000, 1_303_000_000).value
        assert correct < naive


# ===========================================================================
# 9. Mathematically wrong P/B — the core regression
# ===========================================================================
class Test09InvalidPriceToBook:
    def test_the_reported_135x_is_detected_as_wrong(self):
        """570.89 / 385.70 = 1.4801, so a stated 1.35x is a mismatch."""
        result = check_stated_multiple(
            "price_to_book", BRK_PB_CLAIMED, BRK_PRICE, BRK_BVPS_CLAIMED,
            formula_id="price_div_bvps")
        assert result.computed == Decimal("1.4801")
        assert result.record.calculation_status is CalculationStatus.MISMATCH
        assert result.blocks

    def test_the_difference_is_recorded_not_just_corrected(self):
        """§6: register that the original claim was wrong."""
        result = check_stated_multiple(
            "price_to_book", BRK_PB_CLAIMED, BRK_PRICE, BRK_BVPS_CLAIMED,
            formula_id="price_div_bvps")
        summary = result.record.summary()
        assert summary["llm_claimed_value"] == "1.3500"
        assert summary["value"] == "1.4801"
        assert summary["difference"] is not None

    def test_a_correct_claim_passes(self):
        result = check_stated_multiple(
            "price_to_book", "1.4801", BRK_PRICE, BRK_BVPS_CLAIMED,
            formula_id="price_div_bvps")
        assert result.record.calculation_status is CalculationStatus.VERIFIED
        assert not result.blocks

    def test_a_claim_with_no_denominator_is_unsupported(self):
        result = check_stated_multiple(
            "price_to_book", BRK_PB_CLAIMED, BRK_PRICE, None,
            formula_id="price_div_bvps")
        assert result.record.calculation_status is CalculationStatus.UNSUPPORTED


# ===========================================================================
# 10. P/B with a stale accounting period
# ===========================================================================
class Test10StalePeriod:
    def test_q2_book_value_with_a_q3_analysis_is_refused(self):
        record = price_to_book("570.89", "385.70",
                               period_end="2026-09-30",
                               bvps_period_end="2026-06-30")
        assert record.calculation_status is CalculationStatus.REFUSED
        assert "2026-06-30" in record.reason
        assert record.blocks_decision

    def test_matching_periods_are_accepted(self):
        record = price_to_book("570.89", "385.70", period_end="2026-09-30",
                               bvps_period_end="2026-09-30")
        assert record.calculation_status is CalculationStatus.VERIFIED

    def test_mixed_periods_are_reported_cross_agent(self):
        report = check_report_consistency(
            metric_period="2026-06-30", reference_period="2026-09-30",
            metric_name="price_to_book")
        assert report.blocks_decision
        assert "STALE_PERIOD_MIXING" in report.blocking_codes


# ===========================================================================
# 11. EPS GAAP vs adjusted
# ===========================================================================
class Test11EpsDefinition:
    def test_gaap_and_adjusted_are_distinct_metrics(self):
        gaap = earnings_per_share(1000, 100, adjusted=False)
        adj = earnings_per_share(1200, 100, adjusted=True)
        assert gaap.metric == "eps_gaap"
        assert adj.metric == "eps_adjusted"
        assert gaap.unit != adj.unit
        assert gaap.value != adj.value

    def test_formula_id_keeps_the_basis(self):
        assert "gaap" in earnings_per_share(1000, 100).formula_id
        assert "adjusted" in earnings_per_share(1000, 100, adjusted=True).formula_id

    def test_eps_math(self):
        # 1000 / 100 = 10.00 per share
        assert earnings_per_share(1000, 100).value == Decimal("10")


# ===========================================================================
# 12. P/E with incompatible definitions
# ===========================================================================
class Test12PeDefinitions:
    def test_trailing_and_forward_pe_are_different_metrics(self):
        trailing = price_to_earnings(100, 5, basis="gaap", forward=False)
        forward = price_to_earnings(100, 6, basis="adjusted", forward=True)
        assert trailing.metric == "pe_trailing"
        assert forward.metric == "pe_forward"
        assert "trailing_gaap" in trailing.formula_id
        assert "forward_adjusted" in forward.formula_id

    def test_pe_math(self):
        # 570.89 / 30 = 19.0297
        record = price_to_earnings("570.89", 30)
        assert record.value == Decimal("19.0297")

    def test_zero_eps_is_not_a_multiple(self):
        record = price_to_earnings(100, 0)
        assert record.value is None
        assert record.calculation_status is CalculationStatus.NOT_COMPUTABLE


# ===========================================================================
# 13. EMA/SMA and percentage distances
# ===========================================================================
class Test13MovingAverages:
    def test_sma_of_a_known_series(self):
        # Mean of 1..5 is 3
        assert simple_moving_average([1, 2, 3, 4, 5], 5) == Decimal("3.000000")

    def test_sma_uses_the_trailing_window(self):
        # Last three of 1..5 are 3,4,5 -> 4
        assert simple_moving_average([1, 2, 3, 4, 5], 3) == Decimal("4.000000")

    def test_sma_needs_a_full_window(self):
        assert simple_moving_average([1, 2], 5) is None

    def test_ema_of_a_constant_series_is_that_constant(self):
        """An EMA of a flat series is the flat value, whatever the window."""
        assert exponential_moving_average([10] * 30, 10) == Decimal("10.000000")

    def test_ema_reacts_faster_than_sma_to_a_jump(self):
        series = [10] * 20 + [20]
        ema = exponential_moving_average(series, 10)
        sma = simple_moving_average(series, 10)
        assert ema > sma

    def test_vwma_weights_by_volume(self):
        # prices 10,20 with volumes 1,3 -> (10+60)/4 = 17.5
        assert volume_weighted_moving_average([10, 20], [1, 3], 2) == Decimal("17.500000")

    def test_vwma_with_zero_volume_is_none(self):
        assert volume_weighted_moving_average([10, 20], [0, 0], 2) is None

    def test_brk_distances_match_hand_calculation(self):
        assert distance_from_level(BRK_PRICE, BRK_SMA50) == Decimal("9.4582")
        assert distance_from_level(BRK_PRICE, BRK_SMA200) == Decimal("14.7003")
        assert distance_from_level(BRK_PRICE, BRK_HIGH) == Decimal("-2.6283")


# ===========================================================================
# 14. MACD and histogram
# ===========================================================================
class Test14Macd:
    def test_macd_of_a_flat_series_is_zero(self):
        result = macd([100] * 60)
        assert result is not None
        line, signal, histogram = result
        assert line == Decimal("0")
        assert signal == Decimal("0")
        assert histogram == Decimal("0")

    def test_histogram_is_line_minus_signal(self):
        series = [100 + i * 0.5 for i in range(60)]
        line, signal, histogram = macd(series)
        assert histogram == pytest.approx(line - signal, abs=Decimal("0.0001"))

    def test_rising_series_has_a_positive_macd(self):
        series = [100 + i for i in range(60)]
        line, _, _ = macd(series)
        assert line > 0

    def test_insufficient_history_is_none(self):
        assert macd([100] * 10) is None


# ===========================================================================
# 15. Bollinger bandwidth and %B
# ===========================================================================
class Test15Bollinger:
    def test_bands_of_a_known_series(self):
        """20 values 1..20: mean 10.5, population stdev ~5.7663."""
        series = list(range(1, 21))
        bands = bollinger_bands(series)
        assert bands.middle == Decimal("10.500000")
        expected_sd = standard_deviation([float(v) for v in series])
        assert bands.upper == pytest.approx(
            Decimal(repr(10.5 + 2 * expected_sd)), abs=Decimal("0.0001"))

    def test_percent_b_is_position_within_the_bands(self):
        """A price at the upper band is %B = 1, at the lower 0."""
        series = list(range(1, 21))
        bands = bollinger_bands(series)
        at_upper = bollinger_bands(series, price=float(bands.upper))
        at_lower = bollinger_bands(series, price=float(bands.lower))
        assert at_upper.percent_b == pytest.approx(Decimal("1"), abs=Decimal("0.001"))
        assert at_lower.percent_b == pytest.approx(Decimal("0"), abs=Decimal("0.001"))

    def test_bandwidth_is_the_band_span_over_the_middle(self):
        series = list(range(1, 21))
        bands = bollinger_bands(series)
        expected = (bands.upper - bands.lower) / bands.middle * 100
        assert bands.bandwidth_pct == pytest.approx(expected, abs=Decimal("0.001"))

    def test_a_flat_series_has_zero_bandwidth_and_no_percent_b(self):
        bands = bollinger_bands([50] * 25)
        assert bands.bandwidth_pct == Decimal("0")
        assert bands.percent_b is None  # zero-width band: undefined


# ===========================================================================
# 16. ATR and stop loss
# ===========================================================================
class Test16AtrAndStop:
    def test_atr_of_a_constant_range(self):
        """Every bar ranges 10 high-to-low: ATR is 10."""
        highs = [100 + i for i in range(20)]
        lows = [90 + i for i in range(20)]
        closes = [95 + i for i in range(20)]
        atr = average_true_range(highs, lows, closes)
        assert atr is not None
        assert atr == pytest.approx(Decimal("10"), abs=Decimal("0.0001"))

    def test_brk_risk_per_share_and_atr_distance(self):
        """§7: entry 557.00, stop 547.40, ATR 9.408 -> 9.60 and 1.02."""
        risk = Decimal(BRK_ENTRY) - Decimal(BRK_STOP)
        assert risk == Decimal("9.60")
        assert atr_distance(BRK_ENTRY, BRK_STOP, BRK_ATR) == Decimal("1.0204")

    def test_the_reported_25_atr_is_detected_as_wrong(self):
        finding = check_stop_consistency(
            BRK_ENTRY, BRK_STOP, BRK_ATR, stated_atr_distance="2.5")
        assert finding is not None
        assert finding.code == "INVALID_STOP_ATR_DISTANCE"
        assert finding.blocks

    def test_the_correct_102_atr_is_accepted(self):
        assert check_stop_consistency(
            BRK_ENTRY, BRK_STOP, BRK_ATR, stated_atr_distance="1.02") is None

    def test_a_25_atr_stop_implies_533_48(self):
        """The level arithmetic the task names: 557.00 - 2.5*9.408."""
        assert stop_for_atr_multiple(BRK_ENTRY, BRK_ATR, "2.5") == Decimal("533.4800")

    def test_insufficient_atr_history_is_none(self):
        assert average_true_range([100, 101], [99, 100], [99.5, 100.5]) is None


# ===========================================================================
# 17/18. Wrong-side stops, LONG and SHORT
# ===========================================================================
class Test17WrongSideLong:
    def test_a_long_stop_above_entry_is_a_contradiction(self):
        finding = check_stop_consistency("557.00", "560.00", "9.408",
                                         direction="LONG")
        assert finding is not None
        assert finding.code == "STOP_WRONG_SIDE"
        assert finding.blocks

    def test_a_long_stop_at_entry_protects_nothing(self):
        finding = check_stop_consistency("557.00", "557.00", "9.408",
                                         direction="LONG")
        assert finding is not None and finding.code == "STOP_WRONG_SIDE"

    def test_atr_distance_is_none_for_a_wrong_side_long(self):
        assert atr_distance("557.00", "560.00", "9.408", direction="LONG") is None


class Test18WrongSideShort:
    def test_a_short_stop_below_entry_is_a_contradiction(self):
        finding = check_stop_consistency("557.00", "550.00", "9.408",
                                         direction="SHORT")
        assert finding is not None
        assert finding.code == "STOP_WRONG_SIDE"

    def test_a_valid_short_stop_computes_its_distance(self):
        # Short entry 557.00, stop 566.40, ATR 9.408 -> 9.40 / 9.408 = 0.9991
        assert atr_distance("557.00", "566.40", "9.408", direction="SHORT") \
            == Decimal("0.9991")

    def test_a_short_stop_above_entry_is_valid(self):
        assert check_stop_consistency("557.00", "566.40", "9.408",
                                      direction="SHORT") is None


# ===========================================================================
# 19. Position sizing
# ===========================================================================
class Test19Sizing:
    def test_risk_budget_divided_by_risk_per_share(self):
        """1000 / 9.60 = 104 shares — before the exposure cap."""
        from decimal import Decimal as D
        assert int(D("1000") / D("9.60")) == 104

    def test_size_respects_the_risk_budget(self):
        from tradingagents.dataflows.risk_engine import size_position
        result = size_position(557.00, 547.40, 9.408, risk_budget=1000.0,
                               min_atr=0.5)
        assert result.qty > 0
        assert result.planned_risk <= 1000.0

    def test_missing_budget_sizes_nothing(self):
        from tradingagents.dataflows.risk_engine import size_position
        result = size_position(557.00, 547.40, 9.408, risk_budget=None,
                               min_atr=0.5)
        assert result.qty == 0


# ===========================================================================
# 20. Concentration limits
# ===========================================================================
class Test20Concentration:
    def test_the_5_percent_cap_binds_before_the_risk_budget(self):
        """§8: 1% risk allows 104 shares; a 5% cap allows 8."""
        from tradingagents.dataflows.risk_engine import size_with_exposure_cap
        result = size_with_exposure_cap(
            entry=557.00, stop=547.40, atr=9.408,
            risk_budget=1000.0, equity=100_000.0,
            max_symbol_exposure=0.05, direction="LONG", cash=100_000.0,
        )
        assert result.qty == 8
        assert result.binding_constraint == "EXPOSURE_CAP"

    def test_the_tighter_constraint_always_wins(self):
        from tradingagents.dataflows.risk_engine import size_with_exposure_cap
        loose = size_with_exposure_cap(
            entry=557.00, stop=547.40, atr=9.408, risk_budget=1000.0,
            equity=100_000.0, max_symbol_exposure=0.50, cash=100_000.0)
        tight = size_with_exposure_cap(
            entry=557.00, stop=547.40, atr=9.408, risk_budget=1000.0,
            equity=100_000.0, max_symbol_exposure=0.01, cash=100_000.0)
        assert tight.qty < loose.qty


# ===========================================================================
# 21. Insufficient capital
# ===========================================================================
class Test21Capital:
    def test_cash_below_the_notional_blocks_the_size(self):
        from tradingagents.dataflows.risk_engine import size_with_exposure_cap
        result = size_with_exposure_cap(
            entry=557.00, stop=547.40, atr=9.408, risk_budget=1000.0,
            equity=100_000.0, max_symbol_exposure=0.05, cash=100.0)
        assert result.qty == 0
        assert result.reasons

    def test_no_equity_means_no_invented_size(self):
        from tradingagents.dataflows.risk_engine import size_with_exposure_cap
        result = size_with_exposure_cap(
            entry=557.00, stop=547.40, atr=9.408, risk_budget=1000.0,
            equity=None, max_symbol_exposure=0.05)
        assert result.qty == 0


# ===========================================================================
# 22. Multi-tranche risk
# ===========================================================================
class Test22Tranches:
    def test_each_leg_is_priced_on_its_own_geometry(self):
        from tradingagents.dataflows.risk_engine import tranche_risk
        first = tranche_risk(555.00, 542.50, 9.408)
        second = tranche_risk(560.00, 547.00, 9.408)
        assert first.risk_per_share == pytest.approx(12.5)
        assert second.risk_per_share == pytest.approx(13.0)
        assert first.risk_per_share != second.risk_per_share

    def test_aggregate_stays_within_the_budget(self):
        from tradingagents.dataflows.risk_engine import aggregate_tranche_risk
        result = aggregate_tranche_risk(
            [{"entry": 555.0, "stop": 542.5, "atr": 9.408},
             {"entry": 560.0, "stop": 547.0, "atr": 9.408}],
            risk_budget=1000.0, equity=100_000.0, max_symbol_exposure=0.20)
        assert result.total_risk <= 1000.0
        assert not result.blocked


# ===========================================================================
# 23. Gap and slippage
# ===========================================================================
class Test23GapAndSlippage:
    def test_gap_widens_the_stressed_risk(self):
        from tradingagents.dataflows.risk_engine import stress_exit
        stressed = stress_exit(557.00, 547.40, 9.408, gap_atr=1.0,
                               slippage_pct=0.001)
        assert stressed.extra_loss_per_share > 0

    def test_slippage_alone_widens_the_risk(self):
        from tradingagents.dataflows.risk_engine import stress_exit
        clean = stress_exit(557.00, 547.40, 9.408, gap_atr=0.0, slippage_pct=0.0)
        slipped = stress_exit(557.00, 547.40, 9.408, gap_atr=0.0, slippage_pct=0.01)
        assert slipped.extra_loss_per_share > clean.extra_loss_per_share

    def test_sizing_uses_the_stressed_risk(self):
        """A gap-aware budget must size fewer shares than a naive one."""
        from tradingagents.dataflows.risk_engine import size_with_exposure_cap
        plain = size_with_exposure_cap(
            entry=557.00, stop=547.40, atr=9.408, risk_budget=100_000.0,
            equity=10_000_000.0, max_symbol_exposure=0.90, cash=10_000_000.0)
        stressed = size_with_exposure_cap(
            entry=557.00, stop=547.40, atr=9.408, risk_budget=100_000.0,
            equity=10_000_000.0, max_symbol_exposure=0.90, cash=10_000_000.0,
            gap_atr=2.0, slippage_pct=0.01)
        assert stressed.qty < plain.qty


# ===========================================================================
# 24. Wrong values produced by an LLM
# ===========================================================================
class Test24WrongLlmValues:
    def test_a_wrong_percentage_claim_is_a_mismatch(self):
        claim = NumericClaim("c1", "distance_from_sma", Decimal("4.5"),
                             "percent", "market", ClaimKind.COMPUTED)
        result = check_claim(claim, "14.7003")
        assert result.verdict is ClaimVerdict.MISMATCH
        assert result.blocks

    def test_a_correct_percentage_claim_passes(self):
        claim = NumericClaim("c2", "distance_from_sma", Decimal("14.7"),
                             "percent", "market", ClaimKind.COMPUTED)
        result = check_claim(claim, "14.7003")
        assert result.verdict is ClaimVerdict.MATCHES
        assert not result.blocks

    def test_a_wrong_pb_claim_is_a_mismatch(self):
        claim = NumericClaim("c3", "price_to_book", Decimal("1.35"),
                             "multiple", "market", ClaimKind.COMPUTED)
        assert check_claim(claim, "1.4801").verdict is ClaimVerdict.MISMATCH

    def test_the_wrong_113_percent_is_caught(self):
        claim = NumericClaim("c4", "distance_from_high", Decimal("11.3"),
                             "percent", "market", ClaimKind.COMPUTED)
        assert check_claim(claim, "-2.6283").verdict is ClaimVerdict.MISMATCH

    def test_an_unverifiable_claim_blocks(self):
        claim = NumericClaim("c5", "price_to_book", Decimal("1.35"),
                             "multiple", "market", ClaimKind.COMPUTED)
        result = check_claim(claim, None)
        assert result.verdict is ClaimVerdict.NOT_CHECKABLE
        assert result.blocks

    def test_an_estimate_is_accepted_as_a_non_fact(self):
        claim = NumericClaim("c6", "growth", Decimal("8"), "percent",
                             "news", ClaimKind.ESTIMATE)
        result = accept_non_fact(claim)
        assert result.verdict is ClaimVerdict.ACCEPTED_NON_FACT
        assert not result.blocks

    def test_a_computed_claim_cannot_be_accepted_as_a_non_fact(self):
        claim = NumericClaim("c7", "price_to_book", Decimal("1.35"),
                             "multiple", "market", ClaimKind.COMPUTED)
        with pytest.raises(ValueError):
            accept_non_fact(claim)


# ===========================================================================
# 25. Numeric conflicts between agents
# ===========================================================================
class Test25CrossAgentConflicts:
    def test_two_agents_stating_different_distances_conflict(self):
        report = check_report_consistency(
            extracted_claims={
                "market": {"distance_from_sma": [Decimal("4.5")]},
                "trader": {"distance_from_sma": [Decimal("14.7")]},
            })
        assert report.blocks_decision
        assert "CROSS_AGENT_NUMERIC_CONFLICT" in report.blocking_codes

    def test_agreeing_agents_do_not_conflict(self):
        report = check_report_consistency(
            extracted_claims={
                "market": {"distance_from_sma": [Decimal("14.7")]},
                "trader": {"distance_from_sma": [Decimal("14.70")]},
            })
        assert not report.blocks_decision

    def test_extraction_finds_the_claim_in_prose(self):
        claims = extract_claims("It trades 4.5% above SMA200.", "market")
        assert len(claims) == 1
        assert claims[0].value == Decimal("4.5")


# ===========================================================================
# 26. Missing or unverified data
# ===========================================================================
class Test26MissingData:
    def test_a_metric_from_an_llm_is_never_a_fact(self):
        record = metric("price_to_book", "1.4801", formula_id="price_div_bvps",
                        source_status=SourceStatus.LLM_CLAIMED)
        assert not record.is_usable

    def test_a_none_value_is_not_computable(self):
        record = metric("pe", None, formula_id="price_div_eps")
        assert record.calculation_status is CalculationStatus.NOT_COMPUTABLE
        assert record.value is None

    def test_the_registry_returns_none_for_an_unknown_metric(self):
        registry = MetricRegistry()
        assert registry.get("price_to_book") is None
        assert registry.value("price_to_book") is None

    def test_the_registry_does_not_expose_a_refused_value(self):
        registry = MetricRegistry()
        result = check_stated_multiple(
            "price_to_book", "1.35", BRK_PRICE, BRK_BVPS_CLAIMED,
            formula_id="price_div_bvps")
        registry.register(result.record)
        assert registry.value("price_to_book") is None
        assert registry.blocks_decision

    def test_a_claim_against_an_uncomputed_metric_is_unverifiable(self):
        report = check_reports({"market": "P/B of 1.35x here."}, {})
        assert report.blocks_decision
        assert "price_to_book" in report.blocking_labels


# ===========================================================================
# 27. Effective blocking of the paper broker
# ===========================================================================
class Test27PaperBrokerBlocked:
    def test_a_math_failure_produces_no_order(self):
        """§11: the software blocks; it does not ask the model not to buy."""
        verdict = evaluate_math(
            entry=BRK_ENTRY, stop=BRK_STOP, atr=BRK_ATR,
            stated_atr_distance="2.5",
        )
        assert verdict.blocks
        plan = PlanInput(
            ticker="BRK-B", rating="OVERWEIGHT",
            intent="ACCUMULATE_CONDITIONALLY", trigger_met=True,
            risk_blocked=False, market_open=True,
            math_reasons=verdict.reasons,
        )
        decision = evaluate_plan(plan)
        assert decision.action is ExecutionAction.BLOCK
        assert decision.creates_order is False

    def test_the_gate_reports_the_specific_hazard(self):
        verdict = evaluate_math(entry=BRK_ENTRY, stop=BRK_STOP, atr=BRK_ATR,
                                stated_atr_distance="2.5")
        assert GateReason.INVALID_STOP_ATR_DISTANCE in verdict.reasons

    def test_a_contradicted_pb_blocks_with_its_own_code(self):
        registry = MetricRegistry()
        registry.register(check_stated_multiple(
            "price_to_book", BRK_PB_CLAIMED, BRK_PRICE, BRK_BVPS_CLAIMED,
            formula_id="price_div_bvps").record)
        verdict = evaluate_math(registry=registry)
        assert GateReason.INVALID_PRICE_TO_BOOK in verdict.reasons


# ===========================================================================
# 28. A valid simulated execution path
# ===========================================================================
class Test28ValidPath:
    def test_clean_numbers_leave_the_gate_free_to_propose(self):
        """No arithmetic finding: the gate may propose (policy permitting)."""
        verdict = evaluate_math(entry=BRK_ENTRY, stop=BRK_STOP, atr=BRK_ATR,
                                stated_atr_distance="1.02")
        assert not verdict.blocks
        plan = PlanInput(
            ticker="BRK-B", rating="OVERWEIGHT",
            intent="ACCUMULATE_CONDITIONALLY", trigger_met=True,
            risk_blocked=False, market_open=True,
            math_reasons=verdict.reasons,
        )
        decision = evaluate_plan(plan)
        assert decision.action is ExecutionAction.PROPOSE_PAPER_ORDER

    def test_a_consistent_claim_set_does_not_block(self):
        report = check_report_consistency(
            reports={"market": "It trades 14.7% above SMA200."},
            computed_metrics={"distance_from_sma": "14.7003"},
        )
        assert not report.blocks_decision


# ===========================================================================
# 29. BRK-B regression
# ===========================================================================
class Test29BrkRegression:
    def test_the_pb_135_is_refused_and_14801_stated(self):
        result = check_stated_multiple(
            "price_to_book", "1.35", "570.89", "385.70",
            formula_id="price_div_bvps")
        assert result.computed == Decimal("1.4801")
        assert result.blocks

    def test_the_25_atr_stop_is_refused_and_102_stated(self):
        finding = check_stop_consistency("557.00", "547.40", "9.408",
                                         stated_atr_distance="2.5")
        assert finding is not None and finding.blocks
        assert atr_distance("557.00", "547.40", "9.408") == Decimal("1.0204")

    def test_the_negative_113_and_positive_45_are_both_refused(self):
        claims = {
            "market": ("The stock is 11.3% below the 52-week high and "
                       "4.5% above SMA200."),
        }
        report = check_reports(claims, {
            "distance_from_high": "-2.6283",
            "distance_from_sma": "14.7003",
        })
        assert report.blocks_decision
        assert set(report.blocking_labels) == {"distance_from_high",
                                               "distance_from_sma"}

    def test_the_5_percent_cap_gives_8_shares_not_104(self):
        from tradingagents.dataflows.risk_engine import size_with_exposure_cap
        result = size_with_exposure_cap(
            entry=557.00, stop=547.40, atr=9.408, risk_budget=1000.0,
            equity=100_000.0, max_symbol_exposure=0.05, cash=100_000.0)
        assert result.qty == 8
        # Without the cap the risk budget alone would allow ~104.
        assert int(Decimal("1000") / Decimal("9.60")) == 104


# ===========================================================================
# 30. Regression on other instruments
# ===========================================================================
class Test30OtherTickers:
    """The same formulas, other markets and currencies."""

    def test_aapl_percentage_distances(self):
        # 230.00 vs 210.00 is +9.5238%; vs 250.00 is -8.0000%
        assert pct_change("230.00", "210.00") == Decimal("9.5238")
        assert pct_change("230.00", "250.00") == Decimal("-8.0000")

    def test_nvda_cagr_over_three_years(self):
        # (450/100)**(1/3)-1 = 65.0964%
        assert cagr(100, 450, 3) == Decimal("65.0964")

    def test_eni_mi_eur_pb(self):
        # An Italian utility in EUR: 14.20 / 9.80 = 1.4490
        record = price_to_book("14.20", "9.80", period_end="2026-09-30",
                               bvps_period_end="2026-09-30")
        assert record.value == Decimal("1.4490")
        assert record.calculation_status is CalculationStatus.VERIFIED

    def test_a_short_setup_on_another_market(self):
        # Short 14.20 with a stop at 14.90: risk 0.70 per share.
        assert atr_distance("14.20", "14.90", "0.30", direction="SHORT") \
            == Decimal("2.3333")

    def test_unit_conversion_for_a_gbp_report(self):
        """London prices in pence: a GBP million figure still converts."""
        assert convert_unit(2500, Unit.MILLION, Unit.BASE) == Decimal("2500000000")


# ===========================================================================
# Property-based invariants (hypothesis)
# ===========================================================================
class TestProperties:
    """Invariants that must hold for *any* input, not just the chosen cases."""

    def test_pct_change_of_the_same_value_is_zero(self):
        from hypothesis import given, settings, strategies as st

        @settings(max_examples=50, deadline=None)
        @given(st.decimals(min_value=Decimal("0.01"), max_value=Decimal("1e9"),
                           places=2))
        def _check(value: Decimal) -> None:
            assert pct_change(value, value) == Decimal("0.0000")

        _check()

    def test_unit_conversion_round_trips(self):
        from hypothesis import given, settings, strategies as st

        @settings(max_examples=50, deadline=None)
        @given(st.decimals(min_value=Decimal("0.01"), max_value=Decimal("1e12"),
                           places=2))
        def _check(value: Decimal) -> None:
            there = convert_unit(value, Unit.BASE, Unit.MILLION)
            back = convert_unit(there, Unit.MILLION, Unit.BASE)
            assert back == pytest.approx(value, abs=Decimal("0.0001"))

        _check()

    def test_atr_distance_scales_inversely_with_atr(self):
        from hypothesis import given, settings, strategies as st

        @settings(max_examples=50, deadline=None)
        @given(st.decimals(min_value=Decimal("1"), max_value=Decimal("100"),
                           places=2))
        def _check(atr: Decimal) -> None:
            distance = atr_distance(Decimal("557.00"), Decimal("547.40"), atr)
            # risk_per_share is fixed at 9.60, so distance == 9.6 / atr
            assert distance == quantize(Decimal("9.60") / atr, Decimal("0.0001"))
            assert distance > 0

        _check()

    def test_no_division_ever_raises(self):
        """Every ratio helper returns None instead of raising."""
        from hypothesis import given, settings, strategies as st

        @settings(max_examples=50, deadline=None)
        @given(st.decimals(places=2), st.decimals(places=2))
        def _check(a: Decimal, b: Decimal) -> None:
            safe_ratio(a, b)      # must not raise
            pct_change(a, b)      # must not raise
            divide(a, b)          # must not raise

        _check()
