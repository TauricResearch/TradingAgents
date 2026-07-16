"""Pro debate pipeline (Phase 4): evidence -> debate -> gates -> recommendation."""

from tradingagents.pro.pipeline.gates import GateResult, event_gate, risk_gate
from tradingagents.pro.pipeline.graph import (
    PipelineState,
    build_pro_pipeline,
    run_pipeline,
    stream_pipeline,
)
from tradingagents.pro.pipeline.nodes import PipelineNodes, load_pipeline_prompt
from tradingagents.pro.pipeline.schemas import (
    CriticReport,
    DebateTurn,
    JudgeVerdict,
    ReflectionNote,
)
from tradingagents.pro.pipeline.votes import (
    build_vote_breakdown,
    confidence_weighted_consensus,
    votes_from_evidence,
)

__all__ = [
    "GateResult",
    "event_gate",
    "risk_gate",
    "PipelineState",
    "build_pro_pipeline",
    "run_pipeline",
    "stream_pipeline",
    "PipelineNodes",
    "load_pipeline_prompt",
    "CriticReport",
    "DebateTurn",
    "JudgeVerdict",
    "ReflectionNote",
    "build_vote_breakdown",
    "confidence_weighted_consensus",
    "votes_from_evidence",
]
