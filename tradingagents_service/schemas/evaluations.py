from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EvaluationRunStatusValue(str, Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class CreateRunEvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rubric_name: str | None = Field(default=None, min_length=1)
    rubric_version: str | None = Field(default=None, min_length=1)
    evaluator_type: str = Field(default="system", pattern="^(system|llm|human)$")
    evaluator_model: str | None = Field(default=None, min_length=1)
    trace_id: str | None = Field(default=None, min_length=1)


class EvaluationRubricResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rubric_id: UUID
    name: str
    version: str
    scope_type: str
    status: str
    description: str | None = None
    definition: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class EvaluationScoreResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score_id: UUID
    dimension: str
    score: float
    confidence: float
    pass_fail: bool
    basis: str
    rationale: str | None = None
    evidence: dict[str, Any] | None = None
    created_at: datetime


class AnnotationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    annotation_id: UUID
    label: str
    severity: str
    basis: str
    annotator_actor_type: str
    annotator_actor_id: str
    annotator_role: str
    notes: str | None = None
    evidence: dict[str, Any] | None = None
    created_at: datetime


class EvaluationRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluation_run_id: UUID
    target_type: str
    target_id: UUID
    shadow_run_id: UUID | None = None
    rubric_id: UUID
    rubric_name: str | None = None
    rubric_version: str | None = None
    evaluator_type: str
    evaluator_model: str | None = None
    status: EvaluationRunStatusValue
    trace_id: str | None = None
    input: dict[str, Any]
    result: dict[str, Any] | None = None
    error: str | None = None
    scores: list[EvaluationScoreResponse] = Field(default_factory=list)
    annotations: list[AnnotationResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class EvaluationRunListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluations: list[EvaluationRunResponse]


class EvaluationRubricListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rubrics: list[EvaluationRubricResponse]
