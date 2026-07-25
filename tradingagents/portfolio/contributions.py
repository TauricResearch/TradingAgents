"""Measured feature-contribution artifacts for portfolio decision audit."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal


@dataclass(frozen=True)
class FeatureContribution:
    """A model/input feature supplied by a deterministic upstream calculator.

    The contribution is always ``abs(z_score) * importance``.  This module
    does not infer a feature, a z-score, or a causal relationship from prose.
    """

    feature: str
    z_score: float
    importance: float
    direction: Literal["positive", "negative", "risk"]
    evidence_ref: str
    source_artifact_id: str | None = None

    def __post_init__(self) -> None:
        if not self.feature.strip() or not self.evidence_ref.strip():
            raise ValueError("feature and evidence_ref are required")
        if self.source_artifact_id is not None and not self.source_artifact_id.strip():
            raise ValueError("source_artifact_id must be non-empty when supplied")
        if not math.isfinite(self.z_score):
            raise ValueError("z_score must be finite")
        if not math.isfinite(self.importance) or not 0 <= self.importance <= 1:
            raise ValueError("importance must be finite and in [0, 1]")

    @property
    def contribution(self) -> float:
        return abs(self.z_score) * self.importance


@dataclass(frozen=True)
class FeatureContributionArtifact:
    """A typed handoff from a deterministic numeric feature calculator.

    TradingAgents intentionally does not derive z-scores or importances from
    analyst prose.  A calculator that has those measurements may submit this
    small, versioned artifact through :class:`AnalysisRequest`; the runner
    then exposes its contributions to the Portfolio Manager as state.  The
    artifact preserves the calculator and methodology identifiers needed for
    an audit without carrying private model reasoning.
    """

    artifact_id: str
    producer: str
    methodology_ref: str
    as_of_date: str
    contributions: tuple[FeatureContribution, ...]
    schema_version: Literal["measured-feature-contributions/v1"] = (
        "measured-feature-contributions/v1"
    )

    def __post_init__(self) -> None:
        if self.schema_version != "measured-feature-contributions/v1":
            raise ValueError("unsupported feature contribution artifact schema_version")
        for name, value in (
            ("artifact_id", self.artifact_id),
            ("producer", self.producer),
            ("methodology_ref", self.methodology_ref),
        ):
            if not value.strip():
                raise ValueError(f"{name} is required")
        try:
            date.fromisoformat(self.as_of_date)
        except ValueError as exc:
            raise ValueError("as_of_date must use YYYY-MM-DD") from exc
        if not self.contributions:
            raise ValueError("contributions must not be empty")
        rank_feature_contributions(self.contributions, limit=len(self.contributions))

    def to_state(self) -> list[dict[str, object]]:
        """Return JSON-safe state inputs, stamping each item with its artifact."""
        return [
            {
                "feature": item.feature,
                "z_score": item.z_score,
                "importance": item.importance,
                "direction": item.direction,
                "evidence_ref": item.evidence_ref,
                "source_artifact_id": self.artifact_id,
            }
            for item in self.contributions
        ]


def rank_feature_contributions(
    values: tuple[FeatureContribution, ...] | list[FeatureContribution],
    *,
    limit: int = 5,
) -> tuple[FeatureContribution, ...]:
    if limit < 1:
        raise ValueError("limit must be positive")
    unique: dict[str, FeatureContribution] = {}
    for value in values:
        if value.feature in unique:
            raise ValueError(f"duplicate feature: {value.feature}")
        unique[value.feature] = value
    return tuple(
        sorted(unique.values(), key=lambda value: (-value.contribution, value.feature))[:limit]
    )


def feature_contributions_from_dicts(value: object) -> tuple[FeatureContribution, ...]:
    """Decode only a verified JSON-safe feature artifact; reject malformed input."""
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise ValueError("feature contributions must be a list")
    parsed: list[FeatureContribution] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise ValueError("feature contribution must be an object")
        parsed.append(
            FeatureContribution(
                feature=str(item["feature"]),
                z_score=float(item["z_score"]),
                importance=float(item["importance"]),
                direction=str(item["direction"]),
                evidence_ref=str(item["evidence_ref"]),
                source_artifact_id=(
                    str(item["source_artifact_id"])
                    if item.get("source_artifact_id") is not None
                    else None
                ),
            )
        )
    return tuple(parsed)


def feature_contribution_artifact_from_dict(
    value: Mapping[str, object],
) -> FeatureContributionArtifact:
    """Decode a versioned numeric handoff and reject untyped/free-text input."""
    if value.get("schema_version") != "measured-feature-contributions/v1":
        raise ValueError("unsupported feature contribution artifact schema_version")
    raw_contributions = value.get("contributions")
    if not isinstance(raw_contributions, Sequence) or isinstance(raw_contributions, str):
        raise ValueError("artifact contributions must be a list")
    return FeatureContributionArtifact(
        artifact_id=str(value["artifact_id"]),
        producer=str(value["producer"]),
        methodology_ref=str(value["methodology_ref"]),
        as_of_date=str(value["as_of_date"]),
        contributions=feature_contributions_from_dicts(raw_contributions),
        schema_version=str(value["schema_version"]),
    )
