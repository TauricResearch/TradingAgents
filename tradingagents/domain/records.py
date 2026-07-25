"""Immutable records at the Phase 2 storage boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"
    BUDGET_EXHAUSTED = "budget_exhausted"
    PROVIDER_RATE_LIMITED = "provider_rate_limited"


class TrustLevel(StrEnum):
    TRUSTED = "trusted"
    USABLE_WITH_WARNING = "usable_with_warning"
    INSUFFICIENT = "insufficient"


@dataclass(frozen=True)
class AnalysisJob:
    id: str
    request: dict[str, Any]
    status: str
    run_signature: str
    created_at: str
    updated_at: str
    started_at: str | None = None
    finished_at: str | None = None
    error: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    report_id: str | None = None
    advice_id: str | None = None
    cancel_requested: bool = False
    resumable: bool = False
    retry_of_job_id: str | None = None
    retry_attempt: int = 0


@dataclass(frozen=True)
class JobEvent:
    job_id: str
    event_id: int
    event_type: str
    timestamp: str
    data: dict[str, Any]


@dataclass(frozen=True)
class Report:
    id: str
    job_id: str
    created_at: str
    result: dict[str, Any]
    markdown: str
    schema_version: int = 1


@dataclass(frozen=True)
class AdviceVersion:
    id: str
    report_id: str
    version: int
    created_at: str
    action: str
    confidence: str
    reason: str
    eligibility: str
    parent_id: str | None = None
    trust_assessment_id: str | None = None
    trigger_message_ids: tuple[str, ...] = ()
    data_snapshot: dict[str, Any] = field(default_factory=dict)
    model_config: dict[str, Any] = field(default_factory=dict)
    usage: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Conversation:
    id: str
    report_id: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ConversationMessage:
    id: str
    conversation_id: str
    role: str
    content: str
    created_at: str
    source_references: tuple[str, ...] = ()
    refreshed_data: bool = False
    candidate_adjustment: bool = False
    usage_record_id: str | None = None


@dataclass(frozen=True)
class UsageRecord:
    id: str
    job_id: str | None
    conversation_id: str | None
    provider: str
    model: str
    requests: int
    input_tokens: int | None
    output_tokens: int | None
    retries: int
    latency_ms: int
    status: str
    warning: str | None
    created_at: str


@dataclass(frozen=True)
class ProviderCacheEntry:
    provider: str
    symbol: str
    capability: str
    request_params_hash: str
    normalized_payload: dict[str, Any]
    source_reference: str
    retrieved_at: str
    effective_at: str | None
    expires_at: str
    payload_hash: str


@dataclass(frozen=True)
class SourceObservation:
    id: str
    job_id: str | None
    conversation_id: str | None
    source: str
    source_reference: str
    retrieved_at: str
    published_at: str | None
    effective_at: str | None
    raw_hash: str
    cache_status: str
    cache_read_at: str | None = None


@dataclass(frozen=True)
class EvidenceField:
    name: str
    value: Any
    unit: str | None
    source_id: str
    source_reference: str
    retrieved_at: str
    published_at: str | None
    effective_at: str | None
    raw_hash: str
    freshness_status: str
    normalization_warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class TrustAssessment:
    id: str
    job_id: str | None
    conversation_id: str | None
    level: str
    executable: bool
    reason_codes: tuple[str, ...]
    warnings: tuple[str, ...]
    assessed_at: str
    evidence: tuple[EvidenceField, ...] = ()
