"""P0 cases A-E of the 2026-11-09 19:24 report — the numbers it got wrong.

Every expectation is the task's own figure, verified independently before the
code was written:

``A`` EPS 22.43 against 39.76 is **-43.59%**, not the reported -37%
``B`` Bollinger middle 546.488 against price 573.095 is **-4.64%** measured
      against the price, not the reported -10.4%
``C`` Band width is **12.31%** of the middle or **11.73%** of the price — both
      valid, with different denominators, so different names
``D`` VIX 28.18 against 16.61 is **+69.66%**, not the reported +58%
``E`` ATR 6.36 to 9.524 cuts the quantity by **33.22%**, not the asserted
      "40-50%"

Cases B and C carry the deeper lesson: a percentage is only checkable when its
denominator is named. The price-against-level and level-against-price figures
are +4.87% and -4.64% for the same two numbers, so an engine with one
convention would reject a correct report.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from tradingagents.agents.math_tools import (
    calculate_distance_from_level,
    calculate_eps_change,
    calculate_percentage_change,
    calculate_quantity_sensitivity,
)
from tradingagents.dataflows.math.precision import quantize
from tradingagents.dataflows.math.technical import (
    bollinger_bands,
    distance_from_level,
    level_distance_from_price,
)
from tradingagents.dataflows.risk_engine import quantity_sensitivity_to_atr

# The report's figures.
EPS_TTM, EPS_FORWARD = 39.76, 22.43
BOLL_UPPER, BOLL_LOWER, BOLL_MIDDLE = 580.114, 512.863, 546.488
PRICE = 573.095
VIX_PRIOR, VIX_NEW = 16.61, 28.18
ATR_OLD, ATR_NEW = 6.36, 9.524


def _json(tool, **kwargs) -> dict:
    return json.loads(tool.invoke(kwargs))


class TestCaseAEpsChange:
    def test_the_claimed_37_percent_is_wrong(self):
        """22.43 / 39.76 - 1 = -43.59%, not -37%."""
        payload = _json(calculate_eps_change, eps_ttm=EPS_TTM, eps_forward=EPS_FORWARD)
        assert Decimal(payload["value"]) == pytest.approx(Decimal("-43.5865"),
                                                          abs=Decimal("0.001"))
        assert payload["calculation_status"] == "VERIFIED"

    def test_the_claim_is_rejected_by_the_validator(self):
        from tradingagents.dataflows.math.claims import (
            ClaimKind,
            NumericClaim,
            check_claim,
        )

        claim = NumericClaim("c", "eps_change", Decimal("-37"), "percent",
                             "fundamentals", ClaimKind.COMPUTED)
        result = check_claim(claim, "-43.5865")
        assert result.verdict.value == "MISMATCH"
        assert result.blocks is True
        # The delta is far beyond rounding: ~6.6 percentage points.
        assert Decimal("-43.5865") - Decimal("-37") == pytest.approx(
            Decimal("-6.5865"), abs=Decimal("0.001"))

    def test_the_correct_claim_passes(self):
        from tradingagents.dataflows.math.claims import (
            ClaimKind,
            NumericClaim,
            check_claim,
        )

        claim = NumericClaim("c", "eps_change", Decimal("-43.59"), "percent",
                             "fundamentals", ClaimKind.COMPUTED)
        assert check_claim(claim, "-43.5865").verdict.value == "MATCHES"

    def test_a_zero_ttm_eps_has_no_percentage(self):
        payload = _json(calculate_eps_change, eps_ttm=0.0, eps_forward=22.43)
        assert payload["calculation_status"] == "NOT_COMPUTABLE"


class TestCaseBBollingerDistance:
    def test_measuring_the_level_against_the_price_gives_4_64(self):
        """(546.488 / 573.095 - 1) * 100 = -4.6427% — the report's convention."""
        value = level_distance_from_price(PRICE, BOLL_MIDDLE)
        assert value == Decimal("-4.6427")

    def test_measuring_the_price_against_the_level_gives_4_87(self):
        """(573.095 / 546.488 - 1) * 100 = +4.8687% — the other convention."""
        value = distance_from_level(PRICE, BOLL_MIDDLE)
        assert value == Decimal("4.8687")

    def test_the_two_conventions_are_not_negatives_of_each_other(self):
        """A percentage change is not symmetric, so one function cannot serve both."""
        price_first = distance_from_level(PRICE, BOLL_MIDDLE)
        level_first = level_distance_from_price(PRICE, BOLL_MIDDLE)
        assert price_first != -level_first
        assert abs(price_first + level_first) > Decimal("0.2")

    def test_the_tool_names_the_denominator(self):
        by_price = _json(calculate_distance_from_level, price=PRICE,
                         level=BOLL_MIDDLE, denominator="price")
        by_level = _json(calculate_distance_from_level, price=PRICE,
                         level=BOLL_MIDDLE, denominator="level")
        assert Decimal(by_price["value"]) == Decimal("-4.6427")
        assert Decimal(by_level["value"]) == Decimal("4.8687")
        assert by_price["formula_id"] == "level_div_price"
        assert by_level["formula_id"] == "price_div_level"
        assert by_price["metric"] != by_level["metric"]

    def test_the_reported_104_is_rejected_either_way(self):
        """Neither convention yields -10.4%, so the claim is wrong under both."""
        for value in (level_distance_from_price(PRICE, BOLL_MIDDLE),
                      distance_from_level(PRICE, BOLL_MIDDLE)):
            assert abs(value - Decimal("-10.4")) > Decimal("5")


class TestCaseCBollingerWidth:
    def test_the_absolute_width(self):
        assert Decimal(str(BOLL_UPPER)) - Decimal(str(BOLL_LOWER)) == \
            pytest.approx(Decimal("67.251"), abs=Decimal("0.001"))

    def test_width_relative_to_the_middle_is_12_31(self):
        value = quantize((Decimal(str(BOLL_UPPER)) - Decimal(str(BOLL_LOWER)))
                         / Decimal(str(BOLL_MIDDLE)) * 100, Decimal("0.0001"))
        assert value == Decimal("12.3060")

    def test_width_relative_to_the_price_is_11_73(self):
        value = quantize((Decimal(str(BOLL_UPPER)) - Decimal(str(BOLL_LOWER)))
                         / Decimal(str(PRICE)) * 100, Decimal("0.0001"))
        assert value == Decimal("11.7347")

    def test_the_band_summary_carries_both_names_and_denominators(self):
        """Two valid figures must not share one name (§2 case C)."""
        # A price away from the band's centre, which is the case that matters:
        # at a price equal to the middle the two percentages coincide and the
        # distinction would go unnoticed.
        series = [100 + (i % 5) for i in range(25)]
        bands = bollinger_bands(series, price=110.0)
        assert bands is not None
        summary = bands.summary()
        assert "bandwidth_pct" in summary
        assert summary["bandwidth_denominator"] == "middle"
        assert "width_over_price_pct" in summary
        assert summary["width_over_price_denominator"] == "price"
        # And they differ, because the denominators differ.
        assert summary["bandwidth_pct"] != summary["width_over_price_pct"]


class TestCaseDVixChange:
    def test_the_change_is_69_66(self):
        """(28.18 / 16.61 - 1) * 100 = +69.66%, not the reported +58%."""
        payload = _json(calculate_percentage_change,
                        new_value=VIX_NEW, reference_value=VIX_PRIOR)
        assert Decimal(payload["value"]) == pytest.approx(Decimal("69.6568"),
                                                          abs=Decimal("0.001"))

    def test_the_claimed_58_is_rejected(self):
        from tradingagents.dataflows.math.claims import (
            ClaimKind,
            NumericClaim,
            check_claim,
        )

        claim = NumericClaim("c", "vix_change", Decimal("58"), "percent",
                             "market", ClaimKind.COMPUTED)
        assert check_claim(claim, "69.6568").verdict.value == "MISMATCH"


class TestCaseEAtrSizing:
    def test_the_quantity_falls_by_33_22_percent(self):
        """At constant monetary risk the size scales by ATR_old / ATR_new."""
        result = quantity_sensitivity_to_atr(ATR_OLD, ATR_NEW, previous_qty=100)
        assert result.reduction_pct == pytest.approx(33.22, abs=0.01)
        assert result.new_qty == 66
        assert result.ratio == pytest.approx(0.667787, abs=0.0001)

    def test_the_asserted_40_to_50_percent_is_not_supported(self):
        """The report's range is a guess; the engine's answer is 33.22%."""
        result = quantity_sensitivity_to_atr(ATR_OLD, ATR_NEW, previous_qty=100)
        assert result.reduction_pct < 40.0
        assert result.reduction_pct > 30.0

    def test_the_tool_reports_the_formula_it_used(self):
        payload = _json(calculate_quantity_sensitivity,
                        previous_atr=ATR_OLD, new_atr=ATR_NEW, previous_qty=100)
        assert payload["reduction_pct"] == pytest.approx(33.22, abs=0.01)
        assert payload["formula_id"] == "qty_scales_inversely_with_stop_distance"

    def test_a_non_positive_atr_is_not_answerable(self):
        result = quantity_sensitivity_to_atr(0.0, ATR_NEW, previous_qty=100)
        assert result.reduction_pct is None
        assert result.new_qty == 0

    def test_a_falling_atr_increases_the_quantity(self):
        result = quantity_sensitivity_to_atr(ATR_NEW, ATR_OLD, previous_qty=66)
        assert result.reduction_pct < 0  # a negative reduction is an increase
        assert result.new_qty > 66
