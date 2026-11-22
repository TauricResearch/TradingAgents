"""ExperimentManifest contract (implements the approved FR-05 spec).

# Implements: FR-05, NFR-08, NFR-09

Frozen manifest with B's confirmed decisions: four variants B0-B3 (all
non-empty), typed ``metrics_rubric`` (``MetricDef``), an independent
``quality_rubric`` (``QualityRubric``), and ``code_hash`` / ``policy_hash`` /
``manifest_hash``. ``compute_manifest_hash`` is the canonical SHA-256 over the
manifest excluding ``manifest_hash`` (see docs/req/contracts-summary.md §3).

Construction does not require ``manifest_hash == compute_manifest_hash`` (the
hash is verified by the comparison layer against the recorded value); we provide
the canonical computation and ``recompute_hash()``.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_HASH64 = r"^[0-9a-f]{64}$"
_CODE = r"^([0-9a-f]{40}|[0-9a-f]{64})$"
REQUIRED_VARIANTS = ("B0", "B1", "B2", "B3")


class MetricDef(BaseModel):
    """One rubric metric: metric name + comparison + verification metadata."""

    model_config = ConfigDict(extra="forbid")

    metric: str = Field(min_length=1)
    operator: Literal["eq", "lte", "gte", "lt", "gt"]
    threshold: float
    verification: str = Field(min_length=1)
    source: str = Field(min_length=1)
    aggregation: str = Field(min_length=1)
    unit: str = Field(min_length=1)


class QualityRubric(BaseModel):
    """Independent quality-judging policy (three levels, double-blind, etc.)."""

    model_config = ConfigDict(extra="forbid")

    levels: list[str] = Field(min_length=3)
    double_blind: bool
    third_party_adjudication: bool
    llm_judge_assist: bool


def compute_manifest_hash(manifest: ExperimentManifest) -> str:
    """Canonical SHA-256 over the manifest excluding ``manifest_hash``."""
    data = manifest.model_dump(mode="json", exclude={"manifest_hash"})
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ExperimentManifest(BaseModel):
    """Frozen inputs for one controlled comparison across variants."""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_assignment=True)

    manifest_id: str
    created_at: datetime
    target_snapshot_id: str
    model_config_hash: str = Field(pattern=_HASH64)
    prompt_hash: str = Field(pattern=_HASH64)
    code_hash: str = Field(pattern=_CODE)
    policy_hash: str = Field(pattern=_HASH64)
    manifest_hash: str = Field(pattern=_HASH64)
    variants: dict[str, dict[str, Any]]
    metrics_rubric: dict[str, MetricDef]
    quality_rubric: QualityRubric

    @field_validator("created_at")
    @classmethod
    def _require_tz_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware (UTC)")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def _require_variants(self) -> ExperimentManifest:
        for name in REQUIRED_VARIANTS:
            if name not in self.variants:
                raise ValueError(f"manifest is missing required variant: {name}")
            if not self.variants[name]:
                raise ValueError(f"variant {name} must have a non-empty configuration")
        for name in self.variants:
            if name not in REQUIRED_VARIANTS:
                raise ValueError(f"unknown variant: {name}")
        if not self.metrics_rubric:
            raise ValueError("metrics_rubric must be a non-empty mapping")
        return self

    def recompute_hash(self) -> str:
        """Return this manifest's canonical hash (excluding ``manifest_hash``)."""
        return compute_manifest_hash(self)
