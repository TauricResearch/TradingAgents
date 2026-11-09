"""SEC concept reconciliation (§4, T06/T07) against the real filing payload.

The regression this fixes is not arithmetic. Q3 revenue of 74,322 is a true
figure, correctly tagged, for the right quarter, in the right unit — and it is
``RevenueFromContractWithCustomerExcludingAssessedTax``, a *subset* of what the
same filing reports as ``Revenues`` (105,647). The report called the subset the
consolidated total.

No check on the number can detect that. The concept has to be checked, which is
what these tests pin — using the actual Berkshire ``companyfacts`` payload, so
the fixtures cannot drift from what the vendor serves.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tradingagents.dataflows.math.sec_reconciliation import (
    CONCEPT_SCOPES,
    FINANCIAL_METRIC_DEFINITION_MISMATCH,
    SEC_CONCEPT_MISMATCH,
    SEC_METRIC_RECONCILED,
    RevenueScope,
    SecFact,
    quarters_are_comparable,
    reconcile_reported_figure,
    reconcile_revenue,
    sec_facts_from_companyfacts,
)
from tradingagents.graph.data_quality_node import create_data_quality_check

# The real cache, when present. Tests that need it skip rather than fail on a
# machine without it; the synthetic fixtures below cover the same logic.
_CACHE = Path("/root/.tradingagents/cache/sec_edgar/CIK0001067983.json")


def _real_payload() -> dict | None:
    """The cached SEC payload, or None when it is absent *or unreadable*.

    Both ``Path.exists()`` and ``read_text()`` can raise ``PermissionError`` on
    a path the process cannot stat — which is what CI hits, since the cache
    lives under ``/root`` and the runner has no access. Guarding only the read
    was not enough. The synthetic payload covers the same logic, so a machine
    without the cache tests the code instead of failing on the environment.
    """
    try:
        if not _CACHE.exists():
            return None
        return json.loads(_CACHE.read_text())
    except (OSError, PermissionError, json.JSONDecodeError):
        return None


def _revenue_facts(payload: dict) -> list[SecFact]:
    facts: list[SecFact] = []
    for concept in (
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SegmentReportingInformationRevenue",
    ):
        facts.extend(sec_facts_from_companyfacts(payload, concept))
    return facts


def _synthetic_payload() -> dict:
    """The same shape, so the logic is testable without the cache."""
    return {"facts": {"us-gaap": {
        "Revenues": {"units": {"USD": [
            {"val": 105647000000, "start": "2026-07-01", "end": "2026-09-30",
             "fy": 2026, "fp": "Q3", "form": "10-Q", "accn": "0001",
             "frame": "CY2026Q3"},
            {"val": 301130000000, "start": "2026-01-01", "end": "2026-09-30",
             "fy": 2026, "fp": "Q3", "form": "10-Q", "accn": "0001"},
        ]}},
        "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
            {"val": 74322000000, "start": "2026-07-01", "end": "2026-09-30",
             "fy": 2026, "fp": "Q3", "form": "10-Q", "accn": "0001",
             "frame": "CY2026Q3"},
            {"val": 207574000000, "start": "2026-01-01", "end": "2026-09-30",
             "fy": 2026, "fp": "Q3", "form": "10-Q", "accn": "0001"},
        ]}},
    }}}


class TestConceptClassification:
    def test_revenues_is_the_consolidated_total(self):
        assert CONCEPT_SCOPES["Revenues"] is RevenueScope.CONSOLIDATED

    def test_contract_revenue_is_not_consolidated(self):
        """The heart of the defect: a subset tagged as if it were the total."""
        assert (CONCEPT_SCOPES["RevenueFromContractWithCustomerExcludingAssessedTax"]
                is RevenueScope.CONTRACT)

    def test_an_unknown_concept_is_unknown_not_consolidated(self):
        fact = SecFact(concept="SomethingNew", value=1.0, unit="USD",
                       end="2026-09-30")
        assert fact.scope is RevenueScope.UNKNOWN


class TestT06ConsolidatedRevenue:
    def test_the_consolidated_figure_reconciles(self):
        payload = _real_payload() or _synthetic_payload()
        result = reconcile_revenue(105_647_000_000, _revenue_facts(payload),
                                   claimed_as_consolidated=True)
        assert result.blocks_decision is False
        assert SEC_METRIC_RECONCILED in result.codes
        assert result.resolved is not None
        assert result.resolved.concept == "Revenues"

    def test_the_subset_presented_as_consolidated_blocks(self):
        """§4's exact regression: 74,322 called the consolidated total."""
        payload = _real_payload() or _synthetic_payload()
        result = reconcile_revenue(74_322_000_000, _revenue_facts(payload),
                                   claimed_as_consolidated=True)
        assert result.blocks_decision is True
        assert FINANCIAL_METRIC_DEFINITION_MISMATCH in result.codes
        finding = result.findings[0]
        assert finding.expected is not None
        assert finding.expected.value == pytest.approx(105_647_000_000)

    def test_the_message_names_both_concepts(self):
        payload = _real_payload() or _synthetic_payload()
        result = reconcile_revenue(74_322_000_000, _revenue_facts(payload))
        message = result.findings[0].message
        assert "RevenueFromContractWithCustomer" in message
        assert "Revenues" in message

    def test_the_subset_is_legitimate_when_it_says_so(self):
        """A report naming contract revenue is not wrong — it is narrower."""
        payload = _real_payload() or _synthetic_payload()
        result = reconcile_revenue(74_322_000_000, _revenue_facts(payload),
                                   claimed_as_consolidated=False)
        assert result.blocks_decision is False
        assert result.resolved.scope is RevenueScope.CONTRACT


class TestT07IncompatibleConcepts:
    def test_a_figure_absent_from_the_filing_is_refused(self):
        payload = _real_payload() or _synthetic_payload()
        # A figure no filing ever reported, at any scale.
        result = reconcile_revenue(1_234_567_890, _revenue_facts(payload))
        assert result.blocks_decision is True
        assert FINANCIAL_METRIC_DEFINITION_MISMATCH in result.codes

    def test_attributing_a_subset_to_the_total_concept_is_refused(self):
        """Saying `Revenues` while quoting contract revenue is a misattribution."""
        payload = _real_payload() or _synthetic_payload()
        result = reconcile_reported_figure("Revenues", 74_322_000_000,
                                           _revenue_facts(payload))
        assert result.blocks_decision is True
        assert SEC_CONCEPT_MISMATCH in result.codes

    def test_no_revenue_at_all_is_refused_rather_than_passed(self):
        result = reconcile_revenue(None, [])
        assert result.blocks_decision is True

    def test_a_zero_value_does_not_match_anything(self):
        facts = [SecFact(concept="Revenues", value=0.0, unit="USD",
                         end="2026-09-30", start="2026-07-01")]
        result = reconcile_revenue(0.0, facts)
        assert result.blocks_decision is True


class TestPeriodSpans:
    def test_a_year_to_date_figure_is_not_the_quarter(self):
        """301,130 and 105,647 both end 2026-09-30 and are six months apart."""
        payload = _real_payload() or _synthetic_payload()
        facts = _revenue_facts(payload)
        ytd = next(f for f in facts if f.concept == "Revenues"
                   and f.start == "2026-01-01")
        quarter = next(f for f in facts if f.concept == "Revenues"
                       and f.start == "2026-07-01")
        ok, why = quarters_are_comparable(ytd, quarter)
        assert ok is False
        assert "different spans" in why

    def test_the_ytd_subset_is_compared_to_the_ytd_total(self):
        """The right counterpart for 207,574 is 302,089, not the quarter's total."""
        payload = _real_payload() or _synthetic_payload()
        result = reconcile_revenue(207_574_000_000, _revenue_facts(payload))
        assert result.blocks_decision is True
        expected = result.findings[0].expected
        assert expected is not None
        assert expected.start == "2026-01-01"
        assert expected.value == pytest.approx(301_130_000_000)


class TestPreSynthesisWiring:
    def test_the_node_blocks_a_misstated_revenue_before_synthesis(self):
        """§4 requires the check before the Fundamentals Analyst sees it."""
        payload = _real_payload() or _synthetic_payload()
        node = create_data_quality_check(
            filings_provider=lambda t, d: [],
            sec_facts_provider=lambda t, d: payload,
        )
        state = {
            "company_of_interest": "BRK-B",
            "trade_date": "2026-11-09",
            "fundamentals_report": "Q3 total revenue 74,322 million USD.",
        }
        out = node(state)["data_quality_precheck"]
        assert out["blocks_execution"] is True
        assert FINANCIAL_METRIC_DEFINITION_MISMATCH in out["blocking_codes"]
        assert out["sec_reconciliation"]["status"] == "BLOCKED"

    def test_the_node_does_not_block_the_correct_figure(self):
        payload = _real_payload() or _synthetic_payload()
        node = create_data_quality_check(
            filings_provider=lambda t, d: [],
            sec_facts_provider=lambda t, d: payload,
        )
        state = {
            "company_of_interest": "BRK-B",
            "trade_date": "2026-11-09",
            "fundamentals_report": "Q3 total revenue 105,647 million USD.",
        }
        out = node(state)["data_quality_precheck"]
        assert FINANCIAL_METRIC_DEFINITION_MISMATCH not in out["blocking_codes"]

    def test_without_a_payload_the_check_reports_it_did_not_run(self):
        """An unattempted check is null, never a pass."""
        node = create_data_quality_check(
            filings_provider=lambda t, d: [], sec_facts_provider=None)
        state = {
            "company_of_interest": "BRK-B",
            "trade_date": "2026-11-09",
            "fundamentals_report": "Q3 total revenue 74,322 million USD.",
        }
        out = node(state)["data_quality_precheck"]
        assert out["sec_reconciliation"] is None
