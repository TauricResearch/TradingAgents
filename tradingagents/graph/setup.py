"""Graph setup for the structured equity ranking pipeline.

Pipeline stages:
  START → Validation → [veto gate] → Tier 1 (Macro+Liquidity parallel)
        → Tier 2 (8 agents parallel) → Scoring (Archetype+MasterScore)
        → Tier 3 (Bull+Bear parallel → Debate → Risk → FinalDecision)
        → END
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List

from langgraph.graph import END, START, StateGraph

from tradingagents.agents.utils.agent_states import PipelineState

logger = logging.getLogger(__name__)


class StructuredGraphSetup:
    """Builds the structured equity ranking LangGraph."""

    def __init__(self, quick_llm, deep_llm):
        self.quick_llm = quick_llm
        self.deep_llm = deep_llm

    def setup_graph(self):
        """Build and compile the structured pipeline graph."""
        from tradingagents.agents.structured import (
            create_archetype_node,
            create_backlog_node,
            create_bear_case_node,
            create_bull_case_node,
            create_business_quality_node,
            create_crowding_node,
            create_debate_node,
            create_earnings_revisions_node,
            create_entry_timing_node,
            create_final_decision_node,
            create_institutional_flow_node,
            create_liquidity_node,
            create_macro_node,
            create_position_replacement_node,
            create_risk_node,
            create_scoring_node,
            create_sector_rotation_node,
            create_theme_substitution_node,
            create_validation_node,
            create_valuation_node,
        )

        # Create node functions
        # Tier 1: cheap model (or no LLM for validation)
        validation_fn = create_validation_node()
        macro_fn = create_macro_node(self.quick_llm)
        liquidity_fn = create_liquidity_node(self.quick_llm)

        # Tier 2: cheap model for analysis
        bq_fn = create_business_quality_node(self.quick_llm)
        inst_fn = create_institutional_flow_node(self.quick_llm)
        val_fn = create_valuation_node(self.quick_llm)
        et_fn = create_entry_timing_node(self.quick_llm)
        er_fn = create_earnings_revisions_node(self.quick_llm)
        sr_fn = create_sector_rotation_node(self.quick_llm)
        bl_fn = create_backlog_node(self.quick_llm)
        cr_fn = create_crowding_node(self.quick_llm)
        arch_fn = create_archetype_node(self.quick_llm)
        score_fn = create_scoring_node()

        # Portfolio-level: deep model for theme/replacement analysis
        theme_fn = create_theme_substitution_node(self.deep_llm)
        replace_fn = create_position_replacement_node(self.deep_llm)

        # Tier 3: deep model for reasoning/debate
        bull_fn = create_bull_case_node(self.deep_llm)
        bear_fn = create_bear_case_node(self.deep_llm)
        debate_fn = create_debate_node(self.deep_llm)
        risk_fn = create_risk_node(self.deep_llm)
        final_fn = create_final_decision_node(self.deep_llm)

        # Build parallel wrapper nodes
        parallel_tier1 = _create_parallel_node(
            [("macro", macro_fn), ("liquidity", liquidity_fn)],
            "Tier 1",
        )
        parallel_tier2 = _create_parallel_node(
            [
                ("business_quality", bq_fn),
                ("institutional_flow", inst_fn),
                ("valuation", val_fn),
                ("entry_timing", et_fn),
                ("earnings_revisions", er_fn),
                ("sector_rotation", sr_fn),
                ("backlog", bl_fn),
                ("crowding", cr_fn),
            ],
            "Tier 2",
        )
        parallel_bull_bear = _create_parallel_node(
            [("bull_case", bull_fn), ("bear_case", bear_fn)],
            "Bull/Bear",
        )

        # Archetype + Score combined node
        def archetype_and_score(state):
            arch_result = arch_fn(state)
            merged = {**state, **arch_result}
            score_result = score_fn(merged)
            return {**arch_result, **score_result}

        # Theme + Replacement combined node (sequential: theme feeds replacement)
        def theme_and_replacement(state):
            theme_result = theme_fn(state)
            merged = {**state, **theme_result}
            replace_result = replace_fn(merged)
            return {**theme_result, **replace_result}

        # Risk + Final Decision combined node
        def risk_and_decision(state):
            risk_result = risk_fn(state)
            merged = {**state, **risk_result}
            final_result = final_fn(merged)
            return {**risk_result, **final_result}

        # Build graph
        workflow = StateGraph(PipelineState)

        workflow.add_node("Validation", validation_fn)
        workflow.add_node("Tier 1 Analysis", parallel_tier1)
        workflow.add_node("Tier 2 Analysis", parallel_tier2)
        workflow.add_node("Scoring", archetype_and_score)
        workflow.add_node("Portfolio Analysis", theme_and_replacement)
        workflow.add_node("Debate", parallel_bull_bear)
        workflow.add_node("Debate Referee", debate_fn)
        workflow.add_node("Decision", risk_and_decision)

        # Edges
        workflow.add_edge(START, "Validation")
        workflow.add_conditional_edges(
            "Validation",
            _veto_gate,
            {END: END, "continue": "Tier 1 Analysis"},
        )
        workflow.add_edge("Tier 1 Analysis", "Tier 2 Analysis")
        workflow.add_edge("Tier 2 Analysis", "Scoring")
        workflow.add_edge("Scoring", "Portfolio Analysis")
        workflow.add_edge("Portfolio Analysis", "Debate")
        workflow.add_edge("Debate", "Debate Referee")
        workflow.add_edge("Debate Referee", "Decision")
        workflow.add_edge("Decision", END)

        return workflow.compile()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _veto_gate(state: Dict[str, Any]) -> str:
    """Check if validation resulted in a hard veto."""
    if state.get("hard_veto"):
        return END
    validation = state.get("validation") or {}
    if validation.get("veto"):
        return END
    return "continue"


def _create_parallel_node(agent_fns: List[tuple], label: str):
    """Create an async node that runs multiple agent functions in parallel.

    Args:
        agent_fns: List of (name, fn) tuples.
        label: Label for logging.
    """

    async def parallel_node(state):
        t0 = time.time()

        async def run_one(name, fn):
            logger.debug("[%s] %s starting", label, name)
            result = await asyncio.to_thread(fn, state)
            logger.debug("[%s] %s done (%.1fs)", label, name, time.time() - t0)
            return result

        tasks = [run_one(name, fn) for name, fn in agent_fns]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        merged: Dict[str, Any] = {}
        all_flags: list = []
        for (name, _), result in zip(agent_fns, results):
            if isinstance(result, Exception):
                logger.error("[%s] %s failed: %s", label, name, result)
                continue
            flags = result.pop("global_flags", [])
            all_flags.extend(flags)
            merged.update(result)
        if all_flags:
            merged["global_flags"] = all_flags

        logger.info("[%s] completed in %.1fs", label, time.time() - t0)
        return merged

    return parallel_node
