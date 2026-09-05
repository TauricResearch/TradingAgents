"""Optional structured narrative providers for local research runs.

The deterministic workflow remains the default. Providers in this module only
add a validated research narrative after normalized data has been collected;
they do not create trade signals or bypass the risk and backtest layers.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from datetime import date
from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from .agent_contracts import (
    AgentOutputEnvelope,
    AgentOutputSection,
    AgentOutputType,
    ConfidenceLevel,
    EvidenceRef,
)
from .data_contracts import FundamentalSnapshot, NewsItem, PriceBar
from .game_approvals import GameApprovalDigest
from .game_opportunity import GameOpportunitySnapshot
from .game_universe import GameResearchSnapshot


class NarrativeMode(str, Enum):
    """Narrative generation mode exposed by the local job runner."""

    DETERMINISTIC = "deterministic"
    OPENAI_NARRATIVE = "openai_narrative"
    MULTI_AGENT_RESEARCH = "multi_agent_research"


class NarrativeProviderError(RuntimeError):
    """Base error for narrative provider configuration or response failures."""


class NarrativeProviderUnavailableError(NarrativeProviderError):
    """Raised before a run when an explicitly selected provider is unavailable."""


class ResearchNarrativeContext(BaseModel):
    """Validated normalized inputs available to an optional narrative provider."""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1)
    as_of_date: date
    price_bars: list[PriceBar] = Field(default_factory=list)
    fundamentals: list[FundamentalSnapshot] = Field(default_factory=list)
    news: list[NewsItem] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    deterministic_outputs: list[AgentOutputEnvelope] = Field(default_factory=list)
    deterministic_report_markdown: str | None = None
    game_research: GameResearchSnapshot | None = None
    game_approvals: GameApprovalDigest | None = None
    game_opportunity: GameOpportunitySnapshot | None = None


class ResearchNarrativeProvider(Protocol):
    """Provider interface for additive, non-decisional research commentary."""

    def generate(self, context: ResearchNarrativeContext) -> Sequence[AgentOutputEnvelope]:
        """Return validated narrative outputs tied to the supplied context."""


class GeneratedNarrative(BaseModel):
    """Schema returned by an LLM before conversion to the stable envelope."""

    model_config = ConfigDict(frozen=True)

    headline: str = Field(min_length=1, max_length=180)
    summary: str = Field(min_length=1, max_length=2_000)
    supporting_points: list[str] = Field(default_factory=list, max_length=6)
    risks: list[str] = Field(default_factory=list, max_length=6)
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM


class OpenAIResearchNarrativeProvider:
    """OpenAI adapter using the repository's capability-aware LLM client."""

    agent_id = "openai-research-narrative"
    agent_role = "OpenAI Research Narrative"
    prompt_version = "research-narrative-v1"

    def __init__(self, *, model: str, llm: Any):
        self.model = model
        self.llm = llm

    @classmethod
    def from_environment(cls) -> OpenAIResearchNarrativeProvider:
        """Create a provider only when the selected OpenAI setup is explicit."""

        if not os.environ.get("OPENAI_API_KEY", "").strip():
            raise NarrativeProviderUnavailableError(
                "OpenAI narrative mode requires OPENAI_API_KEY. "
                "Leave analysis mode on Deterministic to run without an LLM."
            )
        model = os.environ.get("TRADINGAGENTS_RESEARCH_OPENAI_MODEL", "").strip()
        if not model:
            raise NarrativeProviderUnavailableError(
                "OpenAI narrative mode requires TRADINGAGENTS_RESEARCH_OPENAI_MODEL."
            )
        try:
            from tradingagents.llm_clients.openai_client import OpenAIClient
        except ModuleNotFoundError as error:
            raise NarrativeProviderUnavailableError(
                "OpenAI narrative mode requires the project's optional LLM dependencies."
            ) from error
        return cls(model=model, llm=OpenAIClient(model=model, provider="openai").get_llm())

    def generate(self, context: ResearchNarrativeContext) -> list[AgentOutputEnvelope]:
        """Generate one typed narrative output from normalized research records."""

        try:
            structured_llm = self.llm.with_structured_output(GeneratedNarrative)
            response = structured_llm.invoke(_render_prompt(context))
            narrative = (
                response
                if isinstance(response, GeneratedNarrative)
                else GeneratedNarrative.model_validate(response)
            )
        except Exception as error:
            raise NarrativeProviderError(
                f"OpenAI narrative generation failed: {error}"
            ) from error

        return [
            AgentOutputEnvelope(
                symbol=context.symbol,
                as_of_date=context.as_of_date,
                agent_id=self.agent_id,
                agent_role=self.agent_role,
                output_type=AgentOutputType.COCKPIT_PANEL,
                headline=narrative.headline,
                summary=narrative.summary,
                sections=[
                    AgentOutputSection(
                        title="Narrative observations",
                        bullets=narrative.supporting_points,
                        evidence=context.evidence,
                    )
                ],
                evidence=context.evidence,
                risks=narrative.risks,
                confidence=narrative.confidence,
                metadata={
                    "provider": "openai",
                    "model": self.model,
                    "mode": NarrativeMode.OPENAI_NARRATIVE.value,
                    "prompt_version": self.prompt_version,
                },
            )
        ]


def build_narrative_evidence(
    *,
    symbol: str,
    as_of_date: date,
    price_bars: Sequence[PriceBar],
    fundamentals: Sequence[FundamentalSnapshot],
    news: Sequence[NewsItem],
) -> list[EvidenceRef]:
    """Create deterministic references that an added narrative is allowed to use."""

    evidence: list[EvidenceRef] = []
    if price_bars:
        ordered = sorted(price_bars, key=lambda item: item.date)
        evidence.append(
            EvidenceRef(
                source_id=f"price:{symbol}:{ordered[0].date.isoformat()}:{ordered[-1].date.isoformat()}",
                description=f"{len(ordered)} normalized daily price bars",
                as_of_date=ordered[-1].provenance.as_of_date,
                confidence=0.9,
            )
        )
    if fundamentals:
        latest = max(
            fundamentals,
            key=lambda item: (item.provenance.as_of_date, item.period_end),
        )
        evidence.append(
            EvidenceRef(
                source_id=f"fundamentals:{symbol}:{latest.provenance.as_of_date.isoformat()}",
                description=f"Latest normalized snapshot with {len(latest.metrics)} metrics",
                as_of_date=latest.provenance.as_of_date,
                confidence=0.85,
            )
        )
    if news:
        evidence.append(
            EvidenceRef(
                source_id=f"news:{symbol}:{as_of_date.isoformat()}",
                description=f"{len(news)} normalized news items available by the as-of date",
                as_of_date=as_of_date,
                confidence=0.75,
            )
        )
    return evidence


def build_game_narrative_evidence(
    *,
    game_research: GameResearchSnapshot | None,
    game_approvals: GameApprovalDigest | None,
) -> list[EvidenceRef]:
    """Convert point-in-time game sources into the standard evidence whitelist."""
    evidence: list[EvidenceRef] = []
    if game_research is not None:
        evidence.extend(
            EvidenceRef(
                source_id=f"game:{item.evidence_id}",
                description=item.title,
                as_of_date=item.available_as_of,
                confidence=item.confidence,
            )
            for item in game_research.evidence
        )
    if game_approvals is not None:
        evidence.extend(
            EvidenceRef(
                source_id=f"approval:{item.approval.approval_id}",
                description=(
                    f"Official approval: {item.approval.game_name}; "
                    f"operator {item.approval.operating_entity}"
                ),
                as_of_date=item.approval.available_as_of,
                confidence=item.confidence,
            )
            for item in game_approvals.approvals
        )
    return list({item.source_id: item for item in evidence}.values())

def validate_narrative_outputs(
    context: ResearchNarrativeContext,
    outputs: Sequence[AgentOutputEnvelope],
) -> list[AgentOutputEnvelope]:
    """Reject provider outputs that escape the current research context."""

    validated = list(outputs)
    for output in validated:
        if output.symbol != context.symbol or output.as_of_date != context.as_of_date:
            raise NarrativeProviderError(
                "Narrative output symbol and as-of date must match its research context."
            )
        if output.output_type == AgentOutputType.TRADE_SIGNAL:
            raise NarrativeProviderError("Narrative providers cannot create trade signals.")
    return validated


def _render_prompt(context: ResearchNarrativeContext) -> str:
    """Render a bounded, data-only prompt for structured narrative generation."""

    price_lines = [
        f"- {bar.date.isoformat()}: close={bar.close:.4f}, volume={bar.volume}"
        for bar in sorted(context.price_bars, key=lambda item: item.date)[-10:]
    ]
    latest_fundamentals = (
        max(
            context.fundamentals,
            key=lambda item: (item.provenance.as_of_date, item.period_end),
        )
        if context.fundamentals
        else None
    )
    metric_lines = (
        [f"- {key}: {value}" for key, value in sorted(latest_fundamentals.metrics.items())[:12]]
        if latest_fundamentals
        else []
    )
    news_lines = [
        f"- {item.published_at.date().isoformat()} | {item.provider} | {item.title}"
        for item in sorted(context.news, key=lambda item: item.published_at, reverse=True)[:8]
    ]
    evidence_lines = [
        f"- {item.source_id}: {item.description}" for item in context.evidence
    ]

    return "\n".join(
        [
            "You are an equity-research narrative assistant.",
            "Return only the requested structured response.",
            "Use only the normalized records below. Do not invent prices, events, citations,",
            "ratings, or trading instructions. Do not recommend a position size or trade direction.",
            f"Symbol: {context.symbol}",
            f"As-of date: {context.as_of_date.isoformat()}",
            "Price bars:",
            *(price_lines or ["- None available"]),
            "Latest fundamentals:",
            *(metric_lines or ["- None available"]),
            "News items:",
            *(news_lines or ["- None available"]),
            "Available evidence references:",
            *(evidence_lines or ["- None available"]),
        ]
    )
