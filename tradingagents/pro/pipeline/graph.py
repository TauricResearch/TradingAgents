"""Debate-pipeline graph assembly.

Node order (Phase 4 spec): gather -> Technical Bull <-> Bear (bounded) ->
Macro Bull <-> Bear (bounded) -> Sentiment -> Risk gate -> Critic ->
Reflection -> Judge -> Portfolio Manager -> Execution, with a conditional
rejection edge at every gate to the terminal ``rejected`` node.

Complete path maps are passed to every conditional edge (same defensive
pattern the base framework adopted in #1088).
"""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from tradingagents.contracts import (
    AgentEvidence,
    HistoricalAnalog,
    MarketRegime,
    MarketSnapshot,
    MetricReading,
    ProConfig,
    TradeAction,
    TradeRecommendation,
    VoteBreakdown,
)
from tradingagents.pro.pipeline.nodes import PipelineNodes


class PipelineState(TypedDict, total=False):
    snapshot: MarketSnapshot
    evidence_by_team: dict[str, list[AgentEvidence]]
    quant_metrics: dict[str, MetricReading]
    risk_metrics: dict[str, MetricReading]
    regime: MarketRegime
    debate: list[dict]
    technical_rounds: int
    macro_rounds: int
    gate_results: dict[str, dict]
    historical_analogs: list[HistoricalAnalog]
    memory_context: str
    reflection: dict
    judge_action: TradeAction
    judge_confidence: int
    judge_rationale: str
    vote_breakdown: VoteBreakdown
    recommendation: TradeRecommendation | None
    rejection: dict | None
    execution_status: str | None


def _gate(next_node: str):
    """Router: rejection set -> rejected, else continue to next_node."""

    def route(state: PipelineState) -> str:
        return "rejected" if state.get("rejection") else next_node

    return route


def build_pro_pipeline(llm, config: ProConfig, equity: float = 100_000.0, memory=None):
    """Compile the debate pipeline. ``llm`` follows the structured-output
    interface used throughout the Pro layer (any LangChain chat model);
    ``memory`` is an optional ProMemory for analogs/lessons/win-stats."""
    nodes = PipelineNodes(llm, config, equity, memory=memory)
    graph = StateGraph(PipelineState)

    graph.add_node("gather", nodes.gather)
    graph.add_node("technical_bull", nodes.technical_bull)
    graph.add_node("technical_bear", nodes.technical_bear)
    graph.add_node("macro_bull", nodes.macro_bull)
    graph.add_node("macro_bear", nodes.macro_bear)
    graph.add_node("sentiment", nodes.sentiment)
    graph.add_node("risk_gate", nodes.risk_gate)
    graph.add_node("critic", nodes.critic)
    graph.add_node("reflection", nodes.reflection)
    graph.add_node("judge", nodes.judge)
    graph.add_node("portfolio_manager", nodes.portfolio_manager)
    graph.add_node("execution", nodes.execution)
    graph.add_node("rejected", nodes.rejected)

    graph.add_edge(START, "gather")
    graph.add_conditional_edges(
        "gather", _gate("technical_bull"),
        {"technical_bull": "technical_bull", "rejected": "rejected"},
    )
    graph.add_edge("technical_bull", "technical_bear")

    def technical_router(state: PipelineState) -> str:
        if state["technical_rounds"] < config.max_debate_rounds:
            return "technical_bull"
        return "macro_bull"

    graph.add_conditional_edges(
        "technical_bear", technical_router,
        {"technical_bull": "technical_bull", "macro_bull": "macro_bull"},
    )
    graph.add_edge("macro_bull", "macro_bear")

    def macro_router(state: PipelineState) -> str:
        if state["macro_rounds"] < config.max_debate_rounds:
            return "macro_bull"
        return "sentiment"

    graph.add_conditional_edges(
        "macro_bear", macro_router,
        {"macro_bull": "macro_bull", "sentiment": "sentiment"},
    )
    graph.add_edge("sentiment", "risk_gate")
    graph.add_conditional_edges(
        "risk_gate", _gate("critic"), {"critic": "critic", "rejected": "rejected"}
    )
    graph.add_conditional_edges(
        "critic", _gate("reflection"),
        {"reflection": "reflection", "rejected": "rejected"},
    )
    graph.add_edge("reflection", "judge")
    graph.add_edge("judge", "portfolio_manager")
    graph.add_conditional_edges(
        "portfolio_manager", _gate("execution"),
        {"execution": "execution", "rejected": "rejected"},
    )
    graph.add_edge("execution", END)
    graph.add_edge("rejected", END)
    return graph.compile()


def run_pipeline(
    llm,
    config: ProConfig,
    snapshot: MarketSnapshot,
    equity: float = 100_000.0,
    memory=None,
) -> dict[str, Any]:
    """Build and invoke the pipeline once; returns the final state dict."""
    pipeline = build_pro_pipeline(llm, config, equity, memory=memory)
    return pipeline.invoke({"snapshot": snapshot})
