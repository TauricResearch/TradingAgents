"""Validated wire contracts for the offline research phases."""

from __future__ import annotations

import math
import re
from datetime import date, datetime, timezone
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator


class ResearchContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1


def _utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc)


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def require_strict_evidence_availability(
    rows: tuple[dict[str, Any], ...] | list[dict[str, Any]], cutoff: datetime
) -> None:
    """Reject duplicate, unpublished, or not-yet-observed evidence rows."""
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ValueError("evidence cutoff must be timezone-aware")
    cutoff_utc = _utc(cutoff).timestamp()
    identities: set[tuple[str, str]] = set()
    for row in rows:
        source = row.get("source")
        external_id = row.get("external_id")
        if not isinstance(source, str) or not source:
            raise ValueError("snapshot evidence requires a source")
        if not isinstance(external_id, str) or not external_id:
            raise ValueError("snapshot evidence requires an external_id")
        identity = (source, external_id)
        if identity in identities:
            raise ValueError("snapshot evidence contains a duplicate provider identity")
        identities.add(identity)
        observed = _finite_number(row.get("fetched_utc"), "evidence fetched_utc")
        if observed >= cutoff_utc:
            raise ValueError("snapshot evidence was not observed strictly before cutoff")
        latest_observed = row.get("latest_observed_utc")
        if latest_observed is not None and _finite_number(
            latest_observed, "evidence latest_observed_utc"
        ) >= cutoff_utc:
            raise ValueError(
                "snapshot evidence latest observation was not strictly before cutoff"
            )
        published = _finite_number(row.get("created_utc"), "evidence created_utc")
        if published >= cutoff_utc:
            raise ValueError("snapshot evidence was not published strictly before cutoff")


class SnapshotSlice(ResearchContract):
    """Exact evidence returned for one point-in-time decision boundary."""

    decision_date: date
    decision_cutoff: AwareDatetime
    raw_evidence: tuple[dict[str, Any], ...]
    selection_manifest: dict[str, Any]
    coverage: dict[str, Any]

    @field_validator("decision_cutoff")
    @classmethod
    def normalize_cutoff(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def reject_unavailable_evidence(self) -> SnapshotSlice:
        cutoff = self.decision_cutoff.timestamp()
        require_strict_evidence_availability(self.raw_evidence, self.decision_cutoff)
        as_of = self.selection_manifest.get("as_of_utc")
        if as_of is not None and _finite_number(as_of, "selection as_of_utc") != cutoff:
            raise ValueError("selection manifest cutoff differs from its snapshot")
        manifest_id = self.selection_manifest.get("manifest_id")
        if not isinstance(manifest_id, str) or not manifest_id:
            raise ValueError("snapshot selection manifest requires a stable manifest_id")
        return self


class EvidenceSnapshot(ResearchContract):
    run_id: str = Field(min_length=1, max_length=200)
    build_id: str = Field(pattern=r"^build_[0-9a-f]{24}$")
    protocol_id: str = Field(min_length=1, max_length=200)
    collection_policy_id: str = Field(min_length=1, max_length=200)
    universe: tuple[str, ...] = Field(min_length=1)
    sectors: dict[str, str]
    benchmark: str = Field(min_length=1, max_length=64)
    slices: tuple[SnapshotSlice, ...] = Field(min_length=1)

    @field_validator("universe")
    @classmethod
    def normalize_universe(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(symbol.strip().upper() for symbol in value)
        if any(not symbol for symbol in normalized) or len(set(normalized)) != len(normalized):
            raise ValueError("snapshot universe must contain unique non-empty symbols")
        return normalized

    @field_validator("benchmark")
    @classmethod
    def normalize_benchmark(cls, value: str) -> str:
        return value.strip().upper()

    @model_validator(mode="after")
    def validate_cross_sections(self) -> EvidenceSnapshot:
        if set(self.sectors) != set(self.universe):
            raise ValueError("snapshot sectors must exactly match the universe")
        dates = [item.decision_date for item in self.slices]
        if dates != sorted(dates) or len(set(dates)) != len(dates):
            raise ValueError("snapshot slices must use sorted unique decision dates")
        return self


class ModelCheckpointSpec(ResearchContract):
    """Model identity that must already exist before the evaluated timeline."""

    checkpoint_id: str = Field(min_length=1, max_length=240)
    provider: str = Field(min_length=1, max_length=64)
    requested_model: str = Field(min_length=1, max_length=200)
    available_at: AwareDatetime
    knowledge_cutoff: AwareDatetime
    accepted_returned_models: tuple[str, ...] = ()
    weights_sha256: str | None = None
    tools_enabled: Literal[False] = False

    @field_validator("available_at", "knowledge_cutoff")
    @classmethod
    def normalize_checkpoint_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @field_validator("provider")
    @classmethod
    def normalize_provider(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("weights_sha256")
    @classmethod
    def validate_weights_hash(cls, value: str | None) -> str | None:
        if value is not None and re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError("weights_sha256 must be a lowercase SHA-256 digest")
        return value

    @model_validator(mode="after")
    def validate_checkpoint_identity(self) -> ModelCheckpointSpec:
        if self.knowledge_cutoff > self.available_at:
            raise ValueError("model knowledge cutoff cannot follow checkpoint availability")
        accepted = self.accepted_returned_models or (self.requested_model,)
        if len(set(accepted)) != len(accepted) or any(not value.strip() for value in accepted):
            raise ValueError("accepted returned-model identities must be unique and non-empty")
        return self

    def require_predates(self, cutoffs: tuple[datetime, ...]) -> None:
        if not cutoffs:
            raise ValueError("checkpoint validation requires at least one decision cutoff")
        earliest = min(_utc(value) for value in cutoffs)
        if self.available_at >= earliest:
            raise ValueError("model checkpoint must be available before the tested interval")
        if self.knowledge_cutoff >= earliest:
            raise ValueError("model knowledge cutoff must predate the tested interval")

    @property
    def returned_model_allowlist(self) -> tuple[str, ...]:
        return self.accepted_returned_models or (self.requested_model,)


DecisionStatus = Literal["success", "no_evidence", "failed"]


class DecisionRecord(ResearchContract):
    decision_date: date
    decision_cutoff: AwareDatetime
    status: DecisionStatus
    input_selection_manifest_id: str
    forecast_bundle: dict[str, Any] | None
    target_weights: dict[str, float]
    cash_weight: float
    turnover: float = Field(ge=0.0)
    allocator_diagnostics: dict[str, Any]
    error_type: str | None = None

    @field_validator("decision_cutoff")
    @classmethod
    def normalize_decision_cutoff(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def validate_decision(self) -> DecisionRecord:
        for symbol, weight in self.target_weights.items():
            if not symbol or not math.isfinite(float(weight)) \
                    or not 0.0 <= float(weight) <= 1.0:
                raise ValueError(
                    "long-only target weights must be finite values in [0, 1]"
                )
        if not math.isfinite(self.cash_weight) or not 0.0 <= self.cash_weight <= 1.0:
            raise ValueError("long-only cash weight must be a finite value in [0, 1]")
        if abs(sum(self.target_weights.values()) + self.cash_weight - 1.0) > 1e-9:
            raise ValueError("decision target and cash weights must sum to one")
        if self.status == "success" and self.forecast_bundle is None:
            raise ValueError("successful decision requires a forecast bundle")
        if self.status != "success" and self.forecast_bundle is not None:
            raise ValueError("unsuccessful decision cannot claim a forecast bundle")
        if self.status == "failed" and not self.error_type:
            raise ValueError("failed decision requires a bounded error type")
        if self.status != "failed" and self.error_type is not None:
            raise ValueError("only failed decisions may record an error type")
        return self


class DecisionBatch(ResearchContract):
    run_id: str
    build_id: str = Field(pattern=r"^build_[0-9a-f]{24}$")
    protocol_id: str
    snapshot_artifact_id: str
    snapshot_payload_sha256: str
    checkpoint: ModelCheckpointSpec
    arm: Literal["global_events", "without_public_reaction"]
    universe: tuple[str, ...]
    benchmark: str
    initial_portfolio: dict[str, Any]
    allocator: dict[str, Any]
    decisions: tuple[DecisionRecord, ...]

    @model_validator(mode="after")
    def validate_batch(self) -> DecisionBatch:
        dates = [decision.decision_date for decision in self.decisions]
        if dates != sorted(dates) or len(set(dates)) != len(dates):
            raise ValueError("decision batch dates must be sorted and unique")
        expected = set(self.universe)
        if not self.decisions or any(set(row.target_weights) != expected for row in self.decisions):
            raise ValueError("every decision target must exactly match the universe")
        if self.initial_portfolio != {
            "asset_weights": dict.fromkeys(self.universe, 0.0),
            "cash_weight": 1.0,
        }:
            raise ValueError("decision batch requires the frozen all-cash initial portfolio")
        return self


class OutcomeObservation(ResearchContract):
    provider: str = Field(min_length=1, max_length=120)
    observed_at: AwareDatetime
    vintage_id: str = Field(min_length=1, max_length=240)
    raw_payload_sha256: str
    entry_date: date | None
    exit_date: date | None
    asset_returns: dict[str, float | None]
    benchmark_return: float | None
    cash_return: float = 0.0
    provenance: dict[str, Any]

    @field_validator("observed_at")
    @classmethod
    def normalize_observed_at(cls, value: datetime) -> datetime:
        return _utc(value)

    @field_validator("raw_payload_sha256")
    @classmethod
    def validate_raw_payload_hash(cls, value: str) -> str:
        if re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError("raw_payload_sha256 must be a lowercase SHA-256 digest")
        return value

    @model_validator(mode="after")
    def validate_returns(self) -> OutcomeObservation:
        for value in (*self.asset_returns.values(), self.benchmark_return, self.cash_return):
            if value is not None and not math.isfinite(float(value)):
                raise ValueError("outcome returns must be finite when present")
            if value is not None and float(value) < -1.0:
                raise ValueError("a long-only interval return cannot be below -100%")
        if (self.entry_date is None) != (self.exit_date is None):
            raise ValueError("outcome entry and exit dates must be present together")
        if self.entry_date is not None and self.entry_date >= self.exit_date:
            raise ValueError("outcome entry date must precede exit date")
        complete = self.benchmark_return is not None and all(
            value is not None for value in self.asset_returns.values()
        )
        any_return = self.benchmark_return is not None or any(
            value is not None for value in self.asset_returns.values()
        )
        if complete and self.entry_date is None:
            raise ValueError("complete outcomes require explicit entry and exit dates")
        if any_return and self.entry_date is None:
            raise ValueError("dated outcome returns require explicit entry and exit dates")
        return self


class OutcomeRecord(ResearchContract):
    decision_date: date
    status: Literal["complete", "missing"]
    observation: OutcomeObservation
    error_type: str | None = None

    @model_validator(mode="after")
    def validate_status(self) -> OutcomeRecord:
        missing = any(value is None for value in self.observation.asset_returns.values()) or (
            self.observation.benchmark_return is None
        )
        if (self.status == "missing") != missing:
            raise ValueError("outcome status must reflect missing return values")
        if self.error_type is not None and self.status != "missing":
            raise ValueError("only missing outcomes may record an error type")
        return self


class OutcomeBatch(ResearchContract):
    run_id: str
    build_id: str = Field(pattern=r"^build_[0-9a-f]{24}$")
    decision_artifact_id: str
    decision_payload_sha256: str
    provider: str
    universe: tuple[str, ...]
    benchmark: str
    outcomes: tuple[OutcomeRecord, ...]

    @model_validator(mode="after")
    def validate_batch(self) -> OutcomeBatch:
        dates = [outcome.decision_date for outcome in self.outcomes]
        if dates != sorted(dates) or len(set(dates)) != len(dates):
            raise ValueError("outcome dates must be sorted and unique")
        expected = set(self.universe)
        if not self.outcomes or any(
            set(row.observation.asset_returns) != expected for row in self.outcomes
        ):
            raise ValueError("every outcome must exactly match the universe")
        if any(row.observation.provider != self.provider for row in self.outcomes):
            raise ValueError("every outcome must match the batch provider identity")
        return self


class EvaluationReport(ResearchContract):
    run_id: str
    build_id: str = Field(pattern=r"^build_[0-9a-f]{24}$")
    decision_artifact_id: str
    outcome_artifact_id: str
    intervals_total: int
    intervals_completed: int
    intervals_missing: int
    total_return: float | None
    benchmark_return: float | None
    excess_return: float | None
    max_drawdown: float | None
    mean_interval_return: float | None
    total_turnover: float | None
    interval_returns: tuple[dict[str, Any], ...]
    diagnostics: dict[str, Any]


def parse_contract(model_type, payload: dict[str, Any]):
    """Parse JSON-shaped payloads while retaining strict contract validation."""
    import json

    return model_type.model_validate_json(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    )
