from __future__ import annotations

from tradingagents.agents.claims import build_claim_graph
from tradingagents.agents.source_registry import build_source_registry


def build_skill_registry(final_state: dict, source_registry: dict | None = None, claim_graph: dict | None = None) -> dict:
    registry = source_registry or build_source_registry(final_state)
    graph = claim_graph or build_claim_graph(final_state, registry)
    return {
        "skills": [
            {"skill_id": "market_qa", "label": "Market QA"},
            {"skill_id": "entity_resolution", "label": "Entity resolution"},
            {"skill_id": "source_triage", "label": "Source triage"},
            {"skill_id": "claim_extraction", "label": "Claim extraction"},
            {"skill_id": "macro_regime", "label": "Macro regime"},
            {"skill_id": "risk_policy", "label": "Risk policy"},
            {"skill_id": "judge", "label": "Judge"},
        ],
        "source_registry": registry,
        "claim_graph": graph,
    }
