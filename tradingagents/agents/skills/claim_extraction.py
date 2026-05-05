from __future__ import annotations

from typing import Any

from tradingagents.agents.claims import build_claim_graph


def build_claim_extraction(final_state: dict[str, Any], source_registry: dict[str, Any]) -> dict[str, Any]:
    return build_claim_graph(final_state, source_registry)
