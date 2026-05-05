from __future__ import annotations

from typing import Any


INVALID_RECOMMENDATION_RATING = "invalid_due_to_quality_gate"

_INVALIDATING_WARNING_CODES = {
    "no_explicit_source_reference",
    "recommendation_chain_divergent",
    "scorecard_reconciliation_missing",
}


def _quality_findings(quality: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(quality, dict):
        return []
    findings = quality.get("findings")
    if not isinstance(findings, list):
        return []
    return [finding for finding in findings if isinstance(finding, dict)]


def invalidating_quality_findings(quality: dict[str, Any] | None) -> list[dict[str, Any]]:
    findings = _quality_findings(quality)
    return [
        finding
        for finding in findings
        if finding.get("severity") == "error" or finding.get("code") in _INVALIDATING_WARNING_CODES
    ]


def recommendation_status_from_quality(quality: dict[str, Any] | None) -> str:
    if invalidating_quality_findings(quality):
        return "invalid"
    if isinstance(quality, dict) and quality.get("status") == "passed":
        return "valid"
    if isinstance(quality, dict) and quality.get("status"):
        return "review_required"
    return "not_assessed"


def build_recommendation_contract(
    *,
    final_rating: str | None,
    decision_markdown: str | None,
    quality: dict[str, Any] | None,
    telemetry_summary: dict[str, Any] | None = None,
    target_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    status = recommendation_status_from_quality(quality)
    invalidating = invalidating_quality_findings(quality)
    original_rating = final_rating
    original_markdown = decision_markdown

    if status != "invalid":
        return {
            "recommendation_status": status,
            "invalidated_by_quality_gate": False,
            "final_rating": final_rating,
            "decision_markdown": decision_markdown,
            "original_final_rating": original_rating,
            "invalidating_findings": [],
            "telemetry_summary": telemetry_summary or {},
            "target_profile": target_profile or {},
        }

    finding_lines = [
        f"- {finding.get('code', 'unknown')}: {finding.get('message', 'Quality gate failed.')}"
        for finding in invalidating
    ]
    invalid_markdown = "\n".join(
        [
            "# Recommendation invalidated by quality gate",
            "",
            "This shadow run completed operationally, but it did not produce a valid Buy/Hold/Sell recommendation.",
            "Treat the original model output as audit evidence only.",
            "",
            "Invalidating findings:",
            *(finding_lines or ["- quality_gate_failed: Quality gate failed."]),
            "",
            "Original model output follows for forensic review only.",
            "",
            "---",
            "",
            original_markdown or "",
        ]
    ).strip()
    return {
        "recommendation_status": "invalid",
        "invalidated_by_quality_gate": True,
        "final_rating": INVALID_RECOMMENDATION_RATING,
        "decision_markdown": invalid_markdown,
        "original_final_rating": original_rating,
        "invalidating_findings": invalidating,
        "telemetry_summary": telemetry_summary or {},
        "target_profile": target_profile or {},
    }
