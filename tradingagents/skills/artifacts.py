"""Public, validated methodology scorecards for analyst reports.

The scorecards are deliberately narrower than an analyst's prose report.  They
hold findings, measurements, source references, assumptions that can be
checked later, and declared data gaps.  They must never hold a prompt, a tool
trace, draft text, or private model reasoning.
"""

from __future__ import annotations

from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PublicArtifact(BaseModel):
    """Base contract shared by every persisted methodology scorecard."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["1"] = "1"
    data_as_of: str | None = Field(
        default=None,
        description="As-of date from supplied data, when known (YYYY-MM-DD preferred).",
    )
    limitations: list[str] = Field(
        default_factory=list,
        description="Concrete public data gaps; never hidden reasoning or a tool trace.",
    )


class MetricObservation(BaseModel):
    """A number or an explicit unavailable marker, with a public source reference."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    value: float | None = None
    unit: str | None = Field(default=None, max_length=40)
    source_ref: str | None = Field(default=None, max_length=320)
    availability: Literal["available", "unavailable", "not_applicable"] = "available"

    @model_validator(mode="after")
    def _availability_matches_value(self):
        if self.availability == "available" and self.value is None:
            raise ValueError("available metric observations must include a value")
        if self.availability != "available" and self.value is not None:
            raise ValueError("unavailable metric observations must not include a value")
        return self


class FundamentalsMethodologyArtifact(PublicArtifact):
    """Financial-quality and cycle output requested by the fundamentals skills."""

    dupont_components: dict[str, MetricObservation] = Field(default_factory=dict)
    altman_z_score: MetricObservation | None = None
    beneish_m_score: MetricObservation | None = None
    earnings_quality: str | None = Field(default=None, max_length=600)
    balance_sheet_risk: str | None = Field(default=None, max_length=600)
    cash_conversion: str | None = Field(default=None, max_length=600)
    red_flags: list[str] = Field(default_factory=list, max_length=24)
    cycle_evidence: list[str] = Field(default_factory=list, max_length=12)
    likely_stage: str | None = Field(default=None, max_length=120)
    alternative_stage: str | None = Field(default=None, max_length=120)
    cycle_stage_probabilities: dict[str, float] = Field(default_factory=dict)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _cycle_probabilities_are_probabilities(self):
        if any(not 0.0 <= value <= 1.0 for value in self.cycle_stage_probabilities.values()):
            raise ValueError("cycle stage probabilities must be in [0, 1]")
        total = sum(self.cycle_stage_probabilities.values())
        if total > 1.0001:
            raise ValueError("cycle stage probabilities must not sum above 1")
        return self


class AlphaHypothesis(BaseModel):
    """A dated news-to-financial transmission hypothesis, not a certainty claim."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    event: str = Field(min_length=1, max_length=360)
    event_date: str | None = Field(default=None, max_length=32)
    transmission_chain: str = Field(min_length=1, max_length=800)
    verification_point: str = Field(min_length=1, max_length=400)
    invalidation: str = Field(min_length=1, max_length=400)
    source_ref: str | None = Field(default=None, max_length=320)


class EventSignal(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    event_type: str = Field(min_length=1, max_length=120)
    status: Literal["confirmed", "scheduled", "reported", "rumor", "unavailable"]
    materiality: Literal["low", "medium", "high", "unknown"]
    next_verification: str = Field(min_length=1, max_length=400)
    source_ref: str | None = Field(default=None, max_length=320)


class SectorRotationSignal(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    macro_driver: str = Field(min_length=1, max_length=360)
    affected_sector: str = Field(min_length=1, max_length=160)
    company_exposure: str = Field(min_length=1, max_length=500)
    confidence: float = Field(ge=0.0, le=1.0)
    source_ref: str | None = Field(default=None, max_length=320)


class NewsMethodologyArtifact(PublicArtifact):
    """Validated event, transmission, and sector-rotation findings."""

    alpha_hypotheses: list[AlphaHypothesis] = Field(default_factory=list, max_length=12)
    event_signals: list[EventSignal] = Field(default_factory=list, max_length=12)
    sector_rotation: list[SectorRotationSignal] = Field(default_factory=list, max_length=8)


class RotationSignal(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    sector: str = Field(min_length=1, max_length=160)
    direction: Literal["leading", "improving", "lagging", "unclear"]
    confidence: float = Field(ge=0.0, le=1.0)
    source_ref: str | None = Field(default=None, max_length=320)


class MarketMethodologyArtifact(PublicArtifact):
    """Market regime and health scorecard grounded in verified market data."""

    health_score: MetricObservation | None = None
    trend_regime: str | None = Field(default=None, max_length=180)
    volatility_regime: str | None = Field(default=None, max_length=180)
    participation: str | None = Field(default=None, max_length=360)
    invalidation_levels: list[str] = Field(default_factory=list, max_length=8)
    rotation_signals: list[RotationSignal] = Field(default_factory=list, max_length=12)


class SentimentRealityGapArtifact(PublicArtifact):
    """Public narrative-versus-operating-fact comparison for the sentiment role."""

    narrative: str | None = Field(default=None, max_length=800)
    reality_check: str | None = Field(default=None, max_length=800)
    divergence: Literal["temporary", "structural", "indeterminate", "unavailable"] = "indeterminate"
    reality_gap_score: float | None = Field(default=None, ge=-100.0, le=100.0)
    resolution_trigger: str | None = Field(default=None, max_length=400)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


RoleArtifact: TypeAlias = (
    FundamentalsMethodologyArtifact
    | NewsMethodologyArtifact
    | MarketMethodologyArtifact
    | SentimentRealityGapArtifact
)


ROLE_ARTIFACT_SCHEMAS: dict[str, type[PublicArtifact]] = {
    "fundamentals_analyst": FundamentalsMethodologyArtifact,
    "news_analyst": NewsMethodologyArtifact,
    "market_analyst": MarketMethodologyArtifact,
    "sentiment_analyst": SentimentRealityGapArtifact,
}


def artifact_schema_for_role(role: str) -> type[PublicArtifact]:
    """Return a report schema only for roles with a public analyst artifact."""

    try:
        return ROLE_ARTIFACT_SCHEMAS[role]
    except KeyError as exc:
        raise ValueError(f"no public methodology artifact schema for role: {role}") from exc


def validate_role_artifact(role: str, value: object) -> PublicArtifact:
    """Validate untrusted model JSON against the code-owned public contract."""

    return artifact_schema_for_role(role).model_validate(value)
