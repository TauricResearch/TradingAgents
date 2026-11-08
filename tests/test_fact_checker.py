"""Phase 5 — Fact Checker tests (contract section 6).

The BRK-B claim "the market has already absorbed the Q3" is the regression
case: a causal-inference claim with no supporting facts, published after the
last market session — it must come back REFUTED and blocking. Pure logic,
frozen facts, no network, no LLM.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tradingagents.dataflows.causal_guard import NOT_YET_OBSERVABLE, OBSERVABLE
from tradingagents.dataflows.fact_checker import (
    Claim,
    ClaimClassification,
    ClaimStatus,
    ReasonCode,
    check_claim,
    check_claims,
)
from tradingagents.dataflows.provenance import (
    ProvenanceRegistry,
    unverified_fact,
    verified_fact,
)


def _registry() -> ProvenanceRegistry:
    """A registry with one verified and one quarantined fact."""
    reg = ProvenanceRegistry(snapshot_id="snap-1")
    reg.add(verified_fact(
        "q3_earnings", 12705, "USD_million",
        period="2026-Q3", period_end="2026-09-30",
        source_type="company_release", source_uri="https://example.com/q3",
        published_at=datetime(2026, 11, 7, 12, 0, tzinfo=UTC),
        retrieved_at=datetime(2026, 11, 8, 12, 0, tzinfo=UTC),
        snapshot_id="snap-1",
    ))
    reg.add(verified_fact(
        "close_1106", 570.89, "USD",
        period=None, period_end=None,
        source_type="vendor_api", source_uri="https://example.com/px",
        published_at=datetime(2026, 11, 6, 21, 0, tzinfo=UTC),
        retrieved_at=datetime(2026, 11, 8, 12, 0, tzinfo=UTC),
        snapshot_id="snap-1",
    ))
    reg.add(unverified_fact("stocktwits_target", 633.0, "USD", snapshot_id="snap-1"))
    return reg


# ---------------------------------------------------------------------------
# The BRK-B regression claim (contract §6 example)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_market_absorbed_q3_claim_is_refuted_and_blocking():
    """'Il mercato ha già assorbito il Q3' with no post-event session: REFUTED.

    The contract's own example claim, checked against the weekend case.
    """
    claim = Claim(
        claim_id="C-001",
        statement="Il mercato ha già assorbito il Q3",
        classification=ClaimClassification.CAUSAL_INFERENCE,
        supporting_fact_ids=(),
        blocking=True,
    )
    verdict = check_claim(claim, _registry(), post_event_status=NOT_YET_OBSERVABLE)
    assert verdict.status is ClaimStatus.REFUTED
    assert verdict.reason_code is ReasonCode.EVENT_AFTER_LAST_MARKET_SESSION
    assert verdict.blocks_decision


@pytest.mark.unit
def test_causal_claim_with_unknown_post_event_status_is_unverified():
    claim = Claim("C-2", "the stock absorbed the news",
                  ClaimClassification.CAUSAL_INFERENCE, blocking=True)
    verdict = check_claim(claim, _registry(), post_event_status=None)
    assert verdict.status is ClaimStatus.UNVERIFIED
    assert verdict.reason_code is ReasonCode.POST_EVENT_PRICES_UNAVAILABLE
    assert not verdict.blocks_decision  # unverified, not refuted


@pytest.mark.unit
def test_causal_claim_with_observable_prices_is_not_refuted_for_timing():
    claim = Claim("C-3", "Monday's session absorbed the release",
                  ClaimClassification.CAUSAL_INFERENCE,
                  supporting_fact_ids=("close_1106",))
    verdict = check_claim(claim, _registry(), post_event_status=OBSERVABLE)
    assert verdict.status is ClaimStatus.SUPPORTED


# ---------------------------------------------------------------------------
# Support requirements by classification
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_fact_without_support_is_refuted():
    claim = Claim("C-4", "operating earnings were 12,705M",
                  ClaimClassification.FACT, blocking=True)
    verdict = check_claim(claim, _registry())
    assert verdict.status is ClaimStatus.REFUTED
    assert verdict.reason_code is ReasonCode.NO_SUPPORTING_FACTS
    assert verdict.blocks_decision


@pytest.mark.unit
def test_fact_with_verified_support_is_supported():
    claim = Claim("C-5", "operating earnings were 12,705M",
                  ClaimClassification.FACT,
                  supporting_fact_ids=("q3_earnings",))
    verdict = check_claim(claim, _registry())
    assert verdict.status is ClaimStatus.SUPPORTED
    assert verdict.reason_code is ReasonCode.OK


@pytest.mark.unit
def test_hypothesis_without_support_is_unverified_not_refuted():
    """A labelled opinion is allowed — as long as it stays labelled."""
    claim = Claim("C-6", "buybacks provide a floor",
                  ClaimClassification.HYPOTHESIS)
    verdict = check_claim(claim, _registry())
    assert verdict.status is ClaimStatus.UNVERIFIED
    assert not verdict.blocks_decision


@pytest.mark.unit
def test_blocking_hypothesis_without_support_is_flagged():
    """A *blocking* claim presented as hypothesis without support is the
    HYPOTHESIS_STATED_AS_FACT failure: it cannot block on an opinion."""
    claim = Claim("C-7", "the floor holds", ClaimClassification.HYPOTHESIS,
                  blocking=True)
    verdict = check_claim(claim, _registry())
    assert verdict.status is ClaimStatus.UNVERIFIED
    assert verdict.reason_code is ReasonCode.HYPOTHESIS_STATED_AS_FACT
    assert not verdict.blocks_decision


@pytest.mark.unit
def test_supporting_fact_missing_from_registry_refutes():
    claim = Claim("C-8", "the 633 target is consensus",
                  ClaimClassification.FACT,
                  supporting_fact_ids=("does_not_exist",), blocking=True)
    verdict = check_claim(claim, _registry())
    assert verdict.status is ClaimStatus.REFUTED
    assert verdict.reason_code is ReasonCode.CONTRADICTED_BY_REGISTRY


@pytest.mark.unit
def test_unverified_supporting_fact_downgrades_to_unverified():
    """The StockTwits target is unverified: a claim resting on it cannot
    be presented as supported fact."""
    claim = Claim("C-9", "633 is the fair value",
                  ClaimClassification.FACT,
                  supporting_fact_ids=("stocktwits_target",))
    verdict = check_claim(claim, _registry())
    assert verdict.status is ClaimStatus.UNVERIFIED
    assert verdict.reason_code is ReasonCode.SUPPORTING_FACTS_UNVERIFIED


# ---------------------------------------------------------------------------
# Report-level aggregation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_report_blocks_only_on_refuted_blocking_claims():
    reg = _registry()
    report = check_claims([
        Claim("C-1", "absorbed the Q3", ClaimClassification.CAUSAL_INFERENCE,
              blocking=True),
        Claim("C-2", "buyback floor", ClaimClassification.HYPOTHESIS),
    ], reg, post_event_status=NOT_YET_OBSERVABLE)
    assert report.blocks_decision
    assert report.blocking_claim_ids == ["C-1"]
    assert report.refuted_claim_ids == ["C-1"]
    summary = report.summary()
    assert summary["total_claims"] == 2
    assert summary["refuted"] == 1
    assert summary["blocking_claims"] == ["C-1"]


@pytest.mark.unit
def test_report_without_blocking_refutations_does_not_block():
    reg = _registry()
    report = check_claims([
        Claim("C-1", "earnings were 12,705M", ClaimClassification.FACT,
              supporting_fact_ids=("q3_earnings",)),
        Claim("C-2", "momentum continues", ClaimClassification.FORECAST),
    ], reg, post_event_status=OBSERVABLE)
    assert not report.blocks_decision
    assert report.summary()["supported"] == 1
