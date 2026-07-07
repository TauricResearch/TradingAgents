"""Pro agent layer (Phase 3): one EvidenceAgent runtime, config-driven roster."""

from tradingagents.pro.agents.base import (
    EvidenceAgent,
    EvidenceDraft,
    build_team,
    load_team_template,
    run_agents,
)
from tradingagents.pro.agents.metrics import compute_quant_metrics, compute_risk_metrics
from tradingagents.pro.agents.rendering import RenderedContext, render_context
from tradingagents.pro.agents.roster import (
    MACRO_SPECS,
    NEWS_SENTIMENT_SPECS,
    QUANT_SPECS,
    RISK_SPECS,
    ROSTER,
    SPECS_BY_TEAM,
    TECHNICAL_SPECS,
    spec_by_id,
    specs_for_asset,
)
from tradingagents.pro.agents.specs import AgentSpec

__all__ = [
    "EvidenceAgent",
    "EvidenceDraft",
    "build_team",
    "load_team_template",
    "run_agents",
    "compute_quant_metrics",
    "compute_risk_metrics",
    "RenderedContext",
    "render_context",
    "MACRO_SPECS",
    "NEWS_SENTIMENT_SPECS",
    "QUANT_SPECS",
    "RISK_SPECS",
    "ROSTER",
    "SPECS_BY_TEAM",
    "TECHNICAL_SPECS",
    "spec_by_id",
    "specs_for_asset",
    "AgentSpec",
]
