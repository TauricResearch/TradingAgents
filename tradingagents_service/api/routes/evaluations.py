from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from tradingagents_service.api.dependencies import get_shadow_run_repository
from tradingagents_service.db.models import EvaluationRunStatus
from tradingagents_service.db.repository import ShadowRunRepository
from tradingagents_service.evaluations import (
    DEFAULT_RUBRIC_DEFINITION,
    DEFAULT_RUBRIC_NAME,
    DEFAULT_RUBRIC_VERSION,
    build_shadow_run_evaluation_input,
    compute_shadow_run_evaluation,
)
from tradingagents_service.schemas.evaluations import (
    AnnotationResponse,
    CreateRunEvaluationRequest,
    EvaluationRubricListResponse,
    EvaluationRubricResponse,
    EvaluationRunListResponse,
    EvaluationRunResponse,
    EvaluationRunStatusValue,
    EvaluationScoreResponse,
)

router = APIRouter(prefix="/v1/evaluations", tags=["evaluations"])


@router.get("/rubrics", response_model=EvaluationRubricListResponse)
async def list_evaluation_rubrics(
    status_filter: str | None = Query(default="active", alias="status"),
    repo: ShadowRunRepository = Depends(get_shadow_run_repository),
) -> EvaluationRubricListResponse:
    rubrics = await repo.list_evaluation_rubrics(status=status_filter)
    return EvaluationRubricListResponse(rubrics=[_to_rubric_response(rubric) for rubric in rubrics])


@router.post("/shadow-runs/{run_id}", response_model=EvaluationRunResponse, status_code=status.HTTP_201_CREATED)
async def create_shadow_run_evaluation(
    run_id: UUID,
    request: CreateRunEvaluationRequest | None = None,
    repo: ShadowRunRepository = Depends(get_shadow_run_repository),
) -> EvaluationRunResponse:
    request = request or CreateRunEvaluationRequest()
    run = await repo.get_run_by_id(run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"run not found for run_id={run_id}")
    output = await repo.get_output_by_run_id(run_id)
    if output is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"run has no output to evaluate for run_id={run_id}",
        )

    rubric = await repo.ensure_evaluation_rubric(
        name=request.rubric_name or DEFAULT_RUBRIC_NAME,
        version=request.rubric_version or DEFAULT_RUBRIC_VERSION,
        scope_type="shadow_run",
        status="active",
        description="TradingAgents shadow-run evidence, verification, scoring, and judgement rubric.",
        definition_json=DEFAULT_RUBRIC_DEFINITION,
    )
    artifacts = await repo.get_artifacts_by_run_id(run_id)
    evaluation_input = build_shadow_run_evaluation_input(run=run, output=output, artifacts=artifacts)
    computation = compute_shadow_run_evaluation(
        evaluation_input=evaluation_input,
        evaluator_type=request.evaluator_type,
        evaluator_model=request.evaluator_model,
    )
    evaluation_run = await repo.create_completed_evaluation_run(
        rubric_id=rubric.id,
        target_type="shadow_run",
        target_id=run.id,
        shadow_run_id=run.id,
        evaluator_type=request.evaluator_type,
        evaluator_model=request.evaluator_model,
        input_json=computation.input_json,
        result_json=computation.result_json,
        scores=computation.scores,
        annotation=computation.annotation,
        trace_id=request.trace_id,
    )
    scores = await repo.get_evaluation_scores(evaluation_run.id)
    annotations = await repo.get_annotations_for_target(target_type="shadow_run", target_id=run.id)
    return _to_evaluation_response(evaluation_run, rubric=rubric, scores=scores, annotations=annotations)


@router.get("", response_model=EvaluationRunListResponse)
async def list_evaluation_runs(
    shadow_run_id: UUID | None = Query(default=None),
    status_filter: EvaluationRunStatusValue | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    repo: ShadowRunRepository = Depends(get_shadow_run_repository),
) -> EvaluationRunListResponse:
    runs = await repo.list_evaluation_runs(
        shadow_run_id=shadow_run_id,
        status=EvaluationRunStatus(status_filter.value) if status_filter is not None else None,
        limit=limit,
        offset=offset,
    )
    responses = []
    for run in runs:
        rubric = await repo.get_evaluation_rubric_by_id(run.evaluation_rubric_id)
        scores = await repo.get_evaluation_scores(run.id)
        annotations = await repo.get_annotations_for_target(target_type=run.target_type, target_id=run.target_id)
        responses.append(_to_evaluation_response(run, rubric=rubric, scores=scores, annotations=annotations))
    return EvaluationRunListResponse(evaluations=responses)


@router.get("/{evaluation_run_id}", response_model=EvaluationRunResponse)
async def get_evaluation_run(
    evaluation_run_id: UUID,
    repo: ShadowRunRepository = Depends(get_shadow_run_repository),
) -> EvaluationRunResponse:
    evaluation_run = await repo.get_evaluation_run_by_id(evaluation_run_id)
    if evaluation_run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"evaluation not found for evaluation_run_id={evaluation_run_id}",
        )
    rubric = await repo.get_evaluation_rubric_by_id(evaluation_run.evaluation_rubric_id)
    scores = await repo.get_evaluation_scores(evaluation_run.id)
    annotations = await repo.get_annotations_for_target(
        target_type=evaluation_run.target_type,
        target_id=evaluation_run.target_id,
    )
    return _to_evaluation_response(evaluation_run, rubric=rubric, scores=scores, annotations=annotations)


def _to_rubric_response(rubric) -> EvaluationRubricResponse:
    return EvaluationRubricResponse(
        rubric_id=rubric.id,
        name=rubric.name,
        version=rubric.version,
        scope_type=rubric.scope_type,
        status=rubric.status,
        description=rubric.description,
        definition=rubric.definition_json or {},
        created_at=rubric.created_at,
        updated_at=rubric.updated_at,
    )


def _to_evaluation_response(evaluation_run, *, rubric, scores, annotations) -> EvaluationRunResponse:
    return EvaluationRunResponse(
        evaluation_run_id=evaluation_run.id,
        target_type=evaluation_run.target_type,
        target_id=evaluation_run.target_id,
        shadow_run_id=evaluation_run.shadow_run_id,
        rubric_id=evaluation_run.evaluation_rubric_id,
        rubric_name=rubric.name if rubric is not None else None,
        rubric_version=rubric.version if rubric is not None else None,
        evaluator_type=evaluation_run.evaluator_type,
        evaluator_model=evaluation_run.evaluator_model,
        status=EvaluationRunStatusValue(evaluation_run.status.value),
        trace_id=evaluation_run.trace_id,
        input=evaluation_run.input_json,
        result=evaluation_run.result_json,
        error=evaluation_run.error,
        scores=[
            EvaluationScoreResponse(
                score_id=score.id,
                dimension=score.dimension,
                score=score.score,
                confidence=score.confidence,
                pass_fail=score.pass_fail,
                basis=score.basis,
                rationale=score.rationale,
                evidence=score.evidence_json,
                created_at=score.created_at,
            )
            for score in scores
        ],
        annotations=[
            AnnotationResponse(
                annotation_id=annotation.id,
                label=annotation.label,
                severity=annotation.severity,
                basis=annotation.basis,
                annotator_actor_type=annotation.annotator_actor_type,
                annotator_actor_id=annotation.annotator_actor_id,
                annotator_role=annotation.annotator_role,
                notes=annotation.notes,
                evidence=annotation.evidence_json,
                created_at=annotation.created_at,
            )
            for annotation in annotations
        ],
        created_at=evaluation_run.created_at,
        updated_at=evaluation_run.updated_at,
    )
