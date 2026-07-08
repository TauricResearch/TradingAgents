"""Debate-pipeline graph assembly (Phase 4, enhanced in Phase 6).

Shape:

    prepare -> [five team nodes in parallel] -> join
      -> technical debate <-> (bounded) -> macro debate <-> (bounded)
      -> sentiment -> risk gate -> critic -> reflection -> judge
      -> portfolio manager -> human approval (live only, interrupt)
      -> execution

- Teams fan out from ``prepare`` and merge through a reducer channel.
- Debate stages for teams that produced no evidence are skipped
  dynamically instead of debating an empty record.
- Every gate has a rejection edge to the terminal ``rejected`` node.
- Live mode requires a checkpointer at build time: the human-approval
  interrupt cannot pause/resume without one (fail closed, Constraint 5).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

from tradingagents.contracts import (
    AgentEvidence,
    AgentTeam,
    HistoricalAnalog,
    MarketRegime,
    MarketSnapshot,
    MetricReading,
    ProConfig,
    TradeAction,
    TradeRecommendation,
    TradingMode,
    VoteBreakdown,
)
from tradingagents.pro.pipeline.nodes import TEAM_ORDER, PipelineNodes


def _merge_team_evidence(
    left: dict[str, list[AgentEvidence]] | None,
    right: dict[str, list[AgentEvidence]] | None,
) -> dict[str, list[AgentEvidence]]:
    """Reducer for the parallel team branches; each branch writes its own key."""
    return {**(left or {}), **(right or {})}


class PipelineState(TypedDict, total=False):
    snapshot: MarketSnapshot
    equity: float  # per-run override of the builder's equity (backtests)
    evidence_by_team: Annotated[dict[str, list[AgentEvidence]], _merge_team_evidence]
    quant_metrics: dict[str, MetricReading]
    risk_metrics: dict[str, MetricReading]
    run_timeframe: object  # Timeframe inferred from the snapshot's bars
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
    human_approval: dict
    rejection: dict | None
    execution_status: str | None


def _gate(next_node: str):
    """Router: rejection set -> rejected, else continue to next_node."""

    def route(state: PipelineState) -> str:
        return "rejected" if state.get("rejection") else next_node

    return route


def _has_evidence(state: PipelineState, team: AgentTeam) -> bool:
    return bool(state.get("evidence_by_team", {}).get(team.value))


def _next_stage(state: PipelineState, after: str) -> str:
    """Dynamic routing: skip debate stages whose team produced no evidence."""
    if after == "join" and _has_evidence(state, AgentTeam.TECHNICAL):
        return "technical_bull"
    if after in ("join", "technical") and _has_evidence(state, AgentTeam.MACRO):
        return "macro_bull"
    if after in ("join", "technical", "macro") and _has_evidence(
        state, AgentTeam.NEWS_SENTIMENT
    ):
        return "sentiment"
    return "risk_gate"


def build_pro_pipeline(
    llm,
    config: ProConfig,
    equity: float = 100_000.0,
    memory=None,
    advisor=None,
    checkpointer=None,
    llm_retries: int = 1,
    agent_workers: int = 1,
):
    """Compile the debate pipeline.

    ``llm`` follows the Pro structured-output interface (any LangChain chat
    model). ``checkpointer`` enables pause/resume and is mandatory for live
    mode because the human-approval interrupt depends on it.
    """
    if config.mode is TradingMode.LIVE and checkpointer is None:
        raise ValueError(
            "live mode requires a checkpointer: the human-approval interrupt "
            "cannot pause/resume without one"
        )
    nodes = PipelineNodes(
        llm, config, equity, memory=memory, advisor=advisor,
        llm_retries=llm_retries, agent_workers=agent_workers,
    )
    graph = StateGraph(PipelineState)

    graph.add_node("prepare", nodes.prepare)
    team_names = []
    for team in TEAM_ORDER:
        name = f"team_{team.value}"
        graph.add_node(name, nodes.make_team_node(team))
        team_names.append(name)
    graph.add_node("join", nodes.join)
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
    graph.add_node("human_approval", nodes.human_approval)
    graph.add_node("execution", nodes.execution)
    graph.add_node("rejected", nodes.rejected)

    # fan-out / fan-in
    graph.add_edge(START, "prepare")
    for name in team_names:
        graph.add_edge("prepare", name)
        graph.add_edge(name, "join")

    stage_targets = {
        "technical_bull": "technical_bull",
        "macro_bull": "macro_bull",
        "sentiment": "sentiment",
        "risk_gate": "risk_gate",
        "rejected": "rejected",
    }

    def join_router(state: PipelineState) -> str:
        if state.get("rejection"):
            return "rejected"
        return _next_stage(state, "join")

    graph.add_conditional_edges("join", join_router, stage_targets)
    graph.add_edge("technical_bull", "technical_bear")

    def technical_router(state: PipelineState) -> str:
        if state["technical_rounds"] < config.max_debate_rounds:
            return "technical_bull"
        return _next_stage(state, "technical")

    graph.add_conditional_edges("technical_bear", technical_router, stage_targets)
    graph.add_edge("macro_bull", "macro_bear")

    def macro_router(state: PipelineState) -> str:
        if state["macro_rounds"] < config.max_debate_rounds:
            return "macro_bull"
        return _next_stage(state, "macro")

    graph.add_conditional_edges("macro_bear", macro_router, stage_targets)
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
        "portfolio_manager", _gate("human_approval"),
        {"human_approval": "human_approval", "rejected": "rejected"},
    )
    graph.add_conditional_edges(
        "human_approval", _gate("execution"),
        {"execution": "execution", "rejected": "rejected"},
    )
    graph.add_edge("execution", END)
    graph.add_edge("rejected", END)
    return graph.compile(checkpointer=checkpointer)


def run_pipeline(
    llm,
    config: ProConfig,
    snapshot: MarketSnapshot,
    equity: float = 100_000.0,
    memory=None,
    checkpointer=None,
    thread_id: str | None = None,
    **node_kwargs,
) -> dict[str, Any]:
    """Build and invoke the pipeline once; returns the final state dict."""
    pipeline = build_pro_pipeline(
        llm, config, equity, memory=memory, checkpointer=checkpointer, **node_kwargs
    )
    run_config = {"configurable": {"thread_id": thread_id}} if thread_id else None
    return pipeline.invoke({"snapshot": snapshot}, run_config)


def stream_pipeline(
    llm,
    config: ProConfig,
    snapshot: MarketSnapshot,
    equity: float = 100_000.0,
    memory=None,
    checkpointer=None,
    thread_id: str | None = None,
    **node_kwargs,
) -> Iterator[dict[str, Any]]:
    """Stream per-node state updates as the pipeline executes.

    Yields ``{node_name: partial_update}`` dicts (LangGraph "updates" mode) —
    the dashboard's live debate timeline consumes exactly this.
    """
    pipeline = build_pro_pipeline(
        llm, config, equity, memory=memory, checkpointer=checkpointer, **node_kwargs
    )
    run_config = {"configurable": {"thread_id": thread_id}} if thread_id else None
    yield from pipeline.stream({"snapshot": snapshot}, run_config, stream_mode="updates")
