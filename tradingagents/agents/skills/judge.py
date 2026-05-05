from __future__ import annotations

from typing import Any


def build_judge_context(final_state: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_count": len(final_state.get("source_objects") or []),
        "claim_count": len((final_state.get("claim_graph") or {}).get("claim_objects") or []),
        "scorecard": final_state.get("recommendation_scorecard") or {},
        "note": "Judge only after evidence traceability and scorecard reconciliation are present.",
    }
