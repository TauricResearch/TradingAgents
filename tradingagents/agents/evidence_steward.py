"""Evidence Steward node: gate weak or contradictory evidence before debate."""

from tradingagents.dataflows.evidence import evaluate_and_enrich_evidence


def create_evidence_steward():
    def evidence_steward_node(state):
        return evaluate_and_enrich_evidence(state)

    return evidence_steward_node
