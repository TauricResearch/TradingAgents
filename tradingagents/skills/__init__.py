"""Safe, progressive methodology library for TradingAgents roles.

Skills are local Markdown guidance, not executable plugins.  Role selection is
defined in :mod:`tradingagents.skills.registry` and cannot be changed by an
LLM response or a YAML preset.
"""

from tradingagents.skills.artifacts import (
    FundamentalsMethodologyArtifact,
    MarketMethodologyArtifact,
    NewsMethodologyArtifact,
    SentimentRealityGapArtifact,
)
from tradingagents.skills.registry import (
    ROLE_SKILL_NAMES,
    ROLE_SKILL_TRIGGER_PATTERNS,
    MethodologyArtifact,
    SkillRegistry,
    SkillValidationError,
    build_role_report_contract,
    build_role_skill_prompt,
    build_skill_trigger_context,
    emit_methodology_artifact,
    finalize_role_report,
    persist_role_report,
)

__all__ = [
    "ROLE_SKILL_NAMES",
    "ROLE_SKILL_TRIGGER_PATTERNS",
    "MethodologyArtifact",
    "SkillRegistry",
    "SkillValidationError",
    "FundamentalsMethodologyArtifact",
    "MarketMethodologyArtifact",
    "NewsMethodologyArtifact",
    "SentimentRealityGapArtifact",
    "build_role_skill_prompt",
    "build_skill_trigger_context",
    "build_role_report_contract",
    "emit_methodology_artifact",
    "finalize_role_report",
    "persist_role_report",
]
