from __future__ import annotations

from tradingagents_service.recommendation_contract import (
    INVALID_RECOMMENDATION_RATING,
    build_recommendation_contract,
    recommendation_status_from_quality,
)


def test_quality_gate_failure_invalidates_recommendation() -> None:
    quality = {
        "status": "failed",
        "findings": [
            {
                "code": "unrelated_ticker_mention",
                "severity": "error",
                "message": "Decision mentions unrelated ticker.",
            }
        ],
    }

    contract = build_recommendation_contract(
        final_rating="Buy",
        decision_markdown="Rating: Buy. Also consider NVDA.",
        quality=quality,
    )

    assert contract["recommendation_status"] == "invalid"
    assert contract["invalidated_by_quality_gate"] is True
    assert contract["final_rating"] == INVALID_RECOMMENDATION_RATING
    assert contract["original_final_rating"] == "Buy"
    assert contract["invalidating_findings"][0]["code"] == "unrelated_ticker_mention"
    assert "Original model output follows" in contract["decision_markdown"]


def test_scorecard_reconciliation_warning_invalidates_recommendation() -> None:
    quality = {
        "status": "warning",
        "findings": [
            {
                "code": "scorecard_reconciliation_missing",
                "severity": "warning",
                "message": "Final rating diverges from scorecard.",
            }
        ],
    }

    assert recommendation_status_from_quality(quality) == "invalid"


def test_passed_quality_preserves_recommendation() -> None:
    contract = build_recommendation_contract(
        final_rating="Hold",
        decision_markdown="Rating: Hold [SRC-MARKET-1] [RAW-TOOL-0001].",
        quality={"status": "passed", "findings": []},
        target_profile={"investor_type": "growth", "horizon": "12m"},
    )

    assert contract["recommendation_status"] == "valid"
    assert contract["invalidated_by_quality_gate"] is False
    assert contract["final_rating"] == "Hold"
    assert contract["target_profile"]["investor_type"] == "growth"
