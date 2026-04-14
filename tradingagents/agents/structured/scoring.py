"""Deterministic scoring node — no LLM, pure Python.

Computes master_score, applies confidence penalties, checks hard vetoes,
and assigns position roles. This is the heart of the deterministic pipeline.
"""

from __future__ import annotations

from typing import Any, Dict

from tradingagents.models import (
    DataFlag,
    apply_confidence_penalty,
    assign_position_role,
    compute_master_score,
)


def create_scoring_node():
    """Create the deterministic scoring node (no LLM needed)."""

    def node(state: Dict[str, Any]) -> Dict[str, Any]:
        # Extract scores from each agent output
        bq = (state.get("business_quality") or {}).get("score_0_to_10", 5.0)
        macro = (state.get("macro") or {}).get("macro_alignment_0_to_10", 5.0)
        inst = (state.get("institutional_flow") or {}).get("score_0_to_10", 5.0)
        val = (state.get("valuation") or {}).get("score_0_to_10", 5.0)
        et = (state.get("entry_timing") or {}).get("score_0_to_10", 5.0)
        er = (state.get("earnings_revisions") or {}).get("score_0_to_10", 5.0)
        bl = (state.get("backlog") or {}).get("score_0_to_10", 5.0)
        cr = (state.get("crowding") or {}).get("score_0_to_10", 5.0)

        # Regime adjustment from macro agent
        regime_adj = (state.get("macro") or {}).get("regime_score_adjustment", 0.0)

        master = compute_master_score(
            bq, macro, inst, val, et, er, bl, cr,
            regime_adjustment=regime_adj,
        )

        # Collect all data quality flags
        all_flags = []
        for f in (state.get("global_flags") or []):
            if isinstance(f, dict):
                all_flags.append(DataFlag(**f))
            elif isinstance(f, DataFlag):
                all_flags.append(f)

        hard_veto = state.get("hard_veto", False)
        adjusted = apply_confidence_penalty(master, all_flags, hard_veto)
        role = assign_position_role(adjusted)

        return {
            "master_score": master,
            "adjusted_score": adjusted,
            "position_role": role,
        }

    return node
