"""Evidence Steward node: gate weak or contradictory evidence before debate."""

from __future__ import annotations

import logging

from tradingagents.dataflows.evidence import (
    EvidenceStatus,
    evaluate_and_enrich_evidence,
)

logger = logging.getLogger(__name__)


def create_evidence_steward():
    def evidence_steward_node(state):
        try:
            return evaluate_and_enrich_evidence(state)
        except Exception as exc:
            # Unexpected non-verdict exceptions degrade to a gate-unavailable
            # outcome with the fault recorded, rather than failing the whole
            # run with an evidence-rejection category.
            fault_detail = type(exc).__name__
            logger.warning(
                "Evidence steward failed unexpectedly; degrading to "
                "LOW_CONFIDENCE (fault category: %s)",
                fault_detail,
            )
            report = "\n".join([
                "## Evidence Steward Report",
                "Status: gate unavailable",
                f"Evidence confidence: {EvidenceStatus.LOW_CONFIDENCE.value} "
                "(evidence steward fault)",
                f"Fault category: {fault_detail}",
                "Evidence gate could not complete; downstream agents proceed with "
                "unassessed evidence at reduced conviction.",
            ])
            return {
                "evidence_status": EvidenceStatus.LOW_CONFIDENCE.value,
                "evidence_report": report,
                "evidence_steward_fault": fault_detail,
                "evidence_ledger": None,
                "evidence_ledger_artifact_id": None,
            }

    return evidence_steward_node
