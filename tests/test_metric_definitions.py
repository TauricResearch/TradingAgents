"""Definition reconciliation (§5) — the guard arithmetic cannot provide.

Case B of the 2026-11-09 regression is the reason this module exists: Q3
revenue of 74,322 (a segment figure) was set against 105,647 (the
consolidated total), a 1.42x gap. Any percentage computed across them is
arithmetically perfect and financially meaningless, so the block has to come
from comparing what the figures *mean*.

The tests below pin both directions: a legitimate YoY comparison must pass
(differing quarters are the point of having periods), while a span mismatch,
a basis mismatch or an unlabelled figure must be refused.
"""

from __future__ import annotations

import json

import pytest

from tradingagents.agents.math_tools import validate_metric_definitions
from tradingagents.dataflows.math.consistency import (
    check_definition_mix,
    check_report_consistency,
)
from tradingagents.dataflows.math.definitions import (
    DefinitionKind,
    MetricIdentity,
    ShareCountBasis,
    period_granularity,
    reconcile_definitions,
)


def _identity(definition="consolidated", **kwargs) -> MetricIdentity:
    return MetricIdentity(definition=DefinitionKind(definition), **kwargs)


class TestCaseBRevenueDefinitions:
    def test_segment_against_consolidated_is_refused(self):
        """The regression: 74,322 segment vs 105,647 consolidated."""
        verdict = reconcile_definitions(
            _identity("segment", period="2026-Q3"),
            _identity("consolidated", period="2026-Q3"),
        )
        assert verdict.compatible is False
        assert verdict.blocks_decision is True
        assert "DEFINITION_MISMATCH" in verdict.codes

    def test_the_two_definitions_are_materially_different(self):
        """A 1.42x gap is not noise, which is why blending them matters."""
        segment, consolidated = 74322.0, 105647.0
        assert consolidated / segment == pytest.approx(1.4215, abs=0.001)

    def test_two_consolidated_figures_from_different_quarters_are_fine(self):
        """YoY is the whole purpose of having period labels."""
        verdict = reconcile_definitions(
            _identity(period="2026-Q3"),
            _identity(period="2025-Q3"),
        )
        assert verdict.compatible is True
        assert not verdict.conflicts

    def test_a_quarter_against_a_ttm_figure_is_refused(self):
        """Different spans: a quarter is not comparable with a trailing year."""
        verdict = reconcile_definitions(
            _identity(period="2026-Q3"),
            _identity(period="TTM"),
        )
        assert verdict.compatible is False
        assert "PERIOD_MISMATCH" in verdict.codes

    def test_gaap_against_adjusted_is_refused(self):
        verdict = reconcile_definitions(
            MetricIdentity(definition=DefinitionKind.GAAP, basis="gaap"),
            MetricIdentity(definition=DefinitionKind.ADJUSTED, basis="adjusted"),
        )
        assert verdict.compatible is False
        assert "DEFINITION_MISMATCH" in verdict.codes
        assert "BASIS_MISMATCH" in verdict.codes

    def test_different_currencies_are_refused(self):
        verdict = reconcile_definitions(
            _identity(currency="USD"), _identity(currency="EUR"))
        assert "CURRENCY_MISMATCH" in verdict.codes

    def test_different_unit_scales_are_flagged_for_conversion(self):
        verdict = reconcile_definitions(
            _identity(unit="million"), _identity(unit="base"))
        assert "UNIT_SCALE_DIFFERS" in verdict.codes

    def test_an_unlabelled_figure_is_refused_not_assumed(self):
        """Two numbers without a definition are not thereby compatible."""
        verdict = reconcile_definitions(
            MetricIdentity(), _identity())
        assert verdict.compatible is False
        assert verdict.codes == ("DEFINITION_UNLABELLED",)

    def test_diluted_against_weighted_average_shares_is_refused(self):
        verdict = reconcile_definitions(
            MetricIdentity(definition=DefinitionKind.GAAP,
                           share_count_basis=ShareCountBasis.WEIGHTED_AVERAGE),
            MetricIdentity(definition=DefinitionKind.GAAP,
                           share_count_basis=ShareCountBasis.DILUTED),
        )
        assert "SHARE_BASIS_MISMATCH" in verdict.codes

    def test_every_conflict_is_reported_not_only_the_first(self):
        verdict = reconcile_definitions(
            _identity("segment", currency="USD", unit="million"),
            _identity("consolidated", currency="EUR", unit="base"),
        )
        assert len(verdict.conflicts) >= 3


class TestPeriodGranularity:
    def test_quarter_spellings_are_recognized(self):
        for label in ("2026-Q3", "Q3 2026", "2026Q3", "Q3-2026"):
            assert period_granularity(label) == "quarter", label

    def test_a_bare_year_is_a_year(self):
        assert period_granularity("2026") == "year"
        assert period_granularity("FY2026") == "year"

    def test_ttm_is_its_own_span(self):
        assert period_granularity("TTM") == "ttm"
        assert period_granularity("LTM") == "ttm"

    def test_missing_period_is_none(self):
        assert period_granularity(None) is None
        assert period_granularity("") is None


class TestDefinitionCheckInConsistency:
    def test_a_definition_mix_blocks_the_consistency_report(self):
        report = check_report_consistency(
            left_identity=_identity("segment"),
            right_identity=_identity("consolidated"),
            metric_name="revenue_growth",
        )
        assert report.blocks_decision is True
        assert "DEFINITION_MIX" in report.blocking_codes

    def test_matching_definitions_do_not_block(self):
        report = check_report_consistency(
            left_identity=_identity("consolidated"),
            right_identity=_identity("consolidated"),
            metric_name="revenue_growth",
        )
        assert not report.blocks_decision

    def test_the_finding_names_both_definitions(self):
        finding = check_definition_mix(
            _identity("segment"), _identity("consolidated"), "revenue")
        assert finding is not None
        assert finding.blocks is True
        assert "segment" in finding.message
        assert "consolidated" in finding.message

    def test_absent_identities_add_no_finding(self):
        assert check_definition_mix(None, _identity(), "revenue") is None


class TestDefinitionTool:
    def test_the_tool_reports_the_case_b_conflict(self):
        payload = json.loads(validate_metric_definitions.invoke({
            "left_definition": "segment",
            "right_definition": "consolidated",
            "left_period": "2026-Q3",
            "right_period": "2026-Q3",
        }))
        assert payload["compatible"] is False
        assert payload["blocks_decision"] is True
        assert payload["conflicts"][0]["code"] == "DEFINITION_MISMATCH"

    def test_the_tool_allows_yoy(self):
        payload = json.loads(validate_metric_definitions.invoke({
            "left_definition": "consolidated",
            "right_definition": "consolidated",
            "left_period": "2026-Q3",
            "right_period": "2025-Q3",
        }))
        assert payload["compatible"] is True
        assert payload["blocks_decision"] is False
