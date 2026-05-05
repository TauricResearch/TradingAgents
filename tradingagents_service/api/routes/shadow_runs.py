from __future__ import annotations

from datetime import date
from uuid import UUID

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import PlainTextResponse

from tradingagents_service.api.dependencies import get_shadow_run_repository
from tradingagents_service.db.models import ShadowRunStatus
from tradingagents_service.db.repository import ShadowRunRepository
from tradingagents_service.recommendation_contract import build_recommendation_contract
from tradingagents_service.reporting import (
    build_shadow_run_markdown_report,
    report_output_path,
    save_shadow_run_markdown_report,
)
from tradingagents_service.schemas.shadow_runs import (
    ArtifactItem,
    ArtifactsResponse,
    CreateShadowRunRequest,
    CreateShadowRunResponse,
    DecisionResponse,
    EventItem,
    EventsResponse,
    PrecedentItem,
    PrecedentListResponse,
    RunLinks,
    RunStatus,
    ShadowRunHandoffResponse,
    ShadowRunListResponse,
    ShadowRunResponse,
    TraceResponse,
)
from tradingagents_service.ticker_validation import validate_ticker_for_shadow_run
from tradingagents_service.trace import build_shadow_run_trace, load_state_from_artifacts

router = APIRouter(prefix="/v1/shadow-runs", tags=["shadow-runs"])


def _to_api_status(status_value: ShadowRunStatus) -> RunStatus:
    return RunStatus(status_value.value)


def _target_profile_from_metadata(metadata: dict | None) -> dict[str, object] | None:
    if not isinstance(metadata, dict):
        return None
    target_profile = metadata.get("target_profile")
    return target_profile if isinstance(target_profile, dict) else None


def _to_shadow_run_response(run) -> ShadowRunResponse:
    return ShadowRunResponse(
        run_id=run.id,
        ticker=run.ticker,
        trade_date=run.trade_date,
        selected_analysts=run.selected_analysts,
        status=_to_api_status(run.status),
        created_at=run.created_at,
        updated_at=run.updated_at,
        provider=run.provider,
        model_name=run.model,
        error_message=run.error_message,
        target_profile=_target_profile_from_metadata(getattr(run, "metadata_json", None)),
    )


def _status_value(run_status) -> str:
    return run_status.value if hasattr(run_status, "value") else str(run_status)


def _is_terminal_status(run_status) -> bool:
    return _status_value(run_status) in {
        ShadowRunStatus.SUCCEEDED.value,
        ShadowRunStatus.FAILED.value,
        ShadowRunStatus.CANCELLED.value,
    }


def _recommendation_contract_for_output(out, *, target_profile: dict[str, Any] | None = None) -> tuple[dict, dict]:
    metadata = out.provider_metadata or {}
    quality = metadata.get("quality") or {}
    contract = quality.get("recommendation_contract") if isinstance(quality, dict) else None
    if not isinstance(contract, dict):
        contract = build_recommendation_contract(
            final_rating=out.final_rating,
            decision_markdown=out.decision_markdown,
            quality=quality,
            telemetry_summary=metadata.get("telemetry") if isinstance(metadata.get("telemetry"), dict) else {},
            target_profile=target_profile,
        )
    return quality, contract


def _precedent_item(match) -> PrecedentItem:
    return PrecedentItem(
        run_id=match.run_id,
        ticker=match.ticker,
        trade_date=match.trade_date,
        similarity=match.similarity,
        content_hash=match.content_hash,
        content_text=match.content_text,
        embedding_model=match.embedding_model,
        metadata_json=match.metadata_json,
        created_at=match.created_at,
    )


async def _precedent_matches_for_run(run_id: UUID, repo: ShadowRunRepository, *, limit: int = 10):
    if hasattr(repo, "search_precedents_for_run"):
        return await repo.search_precedents_for_run(run_id=run_id, limit=limit)
    return []


@router.post(
    "",
    response_model=CreateShadowRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={status.HTTP_200_OK: {"model": CreateShadowRunResponse, "description": "Existing run retrieved"}},
)
async def create_shadow_run(
    request: CreateShadowRunRequest,
    response: Response,
    repo: ShadowRunRepository = Depends(get_shadow_run_repository),
) -> CreateShadowRunResponse:
    ticker_validation = validate_ticker_for_shadow_run(request.ticker)
    if not ticker_validation.accepted:
        detail = f"Unknown or invalid ticker '{request.ticker}'."
        if ticker_validation.reason:
            detail = f"{detail} {ticker_validation.reason}."
        if ticker_validation.suggestion:
            detail = f"{detail} Did you mean '{ticker_validation.suggestion}'?"
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)

    idempotency_key = ShadowRunRepository.build_idempotency_key(
        ticker=request.ticker,
        trade_date=request.trade_date,
        selected_analysts=[a.value for a in request.selected_analysts],
        provider=request.provider,
        model=request.model,
    )
    existing_run = await repo.get_run_by_idempotency_key(idempotency_key)
    reused_existing = existing_run is not None
    run = await repo.create_queued_run(
        ticker=request.ticker,
        trade_date=request.trade_date,
        selected_analysts=[a.value for a in request.selected_analysts],
        idempotency_key=idempotency_key,
        provider=request.provider,
        model=request.model,
        metadata_json={"target_profile": request.target_profile or {}},
    )
    if reused_existing:
        response.status_code = status.HTTP_200_OK
    base = f"/v1/shadow-runs/{run.id}"
    return CreateShadowRunResponse(
        run_id=run.id,
        status=_to_api_status(run.status),
        reused_existing=reused_existing,
        submission_kind="retrieved" if reused_existing else "queued",
        links=RunLinks(
            self=base,
            events=f"{base}/events",
            artifacts=f"{base}/artifacts",
            decision=f"{base}/decision",
        ),
    )


@router.get("", response_model=ShadowRunListResponse)
async def list_shadow_runs(
    status_filter: RunStatus | None = Query(default=None, alias="status"),
    ticker: str | None = Query(default=None, min_length=1),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    repo: ShadowRunRepository = Depends(get_shadow_run_repository),
) -> ShadowRunListResponse:
    if date_from is not None and date_to is not None and date_from > date_to:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="date_from must be <= date_to")

    try:
        runs = await repo.list_runs(
            status=ShadowRunStatus(status_filter.value) if status_filter is not None else None,
            ticker=ticker,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            offset=offset,
        )
    except TypeError:
        runs = await repo.list_runs(limit=limit, offset=offset)
    return ShadowRunListResponse(runs=[_to_shadow_run_response(run) for run in runs])


@router.get("/{run_id}", response_model=ShadowRunResponse)
async def get_shadow_run(
    run_id: UUID,
    repo: ShadowRunRepository = Depends(get_shadow_run_repository),
) -> ShadowRunResponse:
    run = await repo.get_run_by_id(run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"run not found for run_id={run_id}")
    return _to_shadow_run_response(run)


@router.get("/{run_id}/events", response_model=EventsResponse)
async def get_shadow_run_events(
    run_id: UUID,
    repo: ShadowRunRepository = Depends(get_shadow_run_repository),
) -> EventsResponse:
    run = await repo.get_run_by_id(run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"events not found for run_id={run_id}")
    events = await repo.get_events_by_run_id(run_id)
    return EventsResponse(
        run_id=run_id,
        events=[
            EventItem(
                event_id=e.id,
                timestamp=e.created_at,
                event_type=e.event_type,
                payload=e.payload,
                sequence=e.sequence,
            )
            for e in events
        ],
    )


@router.get("/{run_id}/artifacts", response_model=ArtifactsResponse)
async def get_shadow_run_artifacts(
    run_id: UUID,
    repo: ShadowRunRepository = Depends(get_shadow_run_repository),
) -> ArtifactsResponse:
    run = await repo.get_run_by_id(run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"artifacts not found for run_id={run_id}")
    artifacts = await repo.get_artifacts_by_run_id(run_id)
    return ArtifactsResponse(
        run_id=run_id,
        artifacts=[
            ArtifactItem(
                artifact_id=a.id,
                kind=a.artifact_type,
                uri=a.path,
                sha256=(a.metadata_json or {}).get("sha256", ""),
                content_type=(a.metadata_json or {}).get("content_type", "application/octet-stream"),
                bytes=int((a.metadata_json or {}).get("bytes", 0)),
            )
            for a in artifacts
        ],
    )


@router.get("/{run_id}/decision", response_model=DecisionResponse)
async def get_shadow_run_decision(
    run_id: UUID,
    repo: ShadowRunRepository = Depends(get_shadow_run_repository),
) -> DecisionResponse:
    run = await repo.get_run_by_id(run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"decision not found for run_id={run_id}")
    out = await repo.get_output_by_run_id(run_id)
    if out is None:
        return DecisionResponse(run_id=run_id, target_profile=_target_profile_from_metadata(getattr(run, "metadata_json", None)))
    metadata = out.provider_metadata or {}
    target_profile = _target_profile_from_metadata(getattr(run, "metadata_json", None))
    quality, contract = _recommendation_contract_for_output(out, target_profile=target_profile)
    precedents = await _precedent_matches_for_run(run_id, repo, limit=3)
    return DecisionResponse(
        run_id=run_id,
        final_rating=contract.get("final_rating"),
        final_decision_markdown=contract.get("decision_markdown"),
        recommendation_status=contract.get("recommendation_status"),
        invalidated_by_quality_gate=bool(contract.get("invalidated_by_quality_gate")),
        original_final_rating=contract.get("original_final_rating"),
        invalidating_findings=contract.get("invalidating_findings") or [],
        state_log_dir=out.state_log_dir,
        memory_log_path=out.memory_log_path,
        provider=metadata.get("provider"),
        deep_model=metadata.get("deep_model"),
        quick_model=metadata.get("quick_model"),
        quality_status=quality.get("status"),
        quality_findings=quality.get("findings") or [],
        source_summary=quality.get("source_summary"),
        recommendation_audit=quality.get("recommendation_audit"),
        telemetry_summary=metadata.get("telemetry"),
        target_profile=target_profile,
        precedent_summary={
            "precedent_count": len(precedents),
            "precedents": [_precedent_item(match).model_dump() for match in precedents],
        },
    )


@router.get("/{run_id}/trace", response_model=TraceResponse)
async def get_shadow_run_trace(
    run_id: UUID,
    repo: ShadowRunRepository = Depends(get_shadow_run_repository),
) -> TraceResponse:
    run = await repo.get_run_by_id(run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"trace not found for run_id={run_id}")
    events = await repo.get_events_by_run_id(run_id)
    artifacts = await repo.get_artifacts_by_run_id(run_id)
    output = await repo.get_output_by_run_id(run_id)
    evaluations = []
    if hasattr(repo, "list_evaluation_runs"):
        evaluations = await repo.list_evaluation_runs(shadow_run_id=run_id, limit=1, offset=0)
    precedents = await _precedent_matches_for_run(run_id, repo, limit=3)
    trace = build_shadow_run_trace(
        run=run,
        output=output,
        events=events,
        artifacts=artifacts,
        state=load_state_from_artifacts(artifacts, trade_date=run.trade_date),
        evaluations=evaluations,
    )
    trace["precedent_summary"] = {
        "precedent_count": len(precedents),
        "precedents": [_precedent_item(match).model_dump() for match in precedents],
    }
    return TraceResponse(run_id=run_id, **trace)


@router.get("/{run_id}/handoff", response_model=ShadowRunHandoffResponse)
async def get_shadow_run_handoff(
    run_id: UUID,
    repo: ShadowRunRepository = Depends(get_shadow_run_repository),
) -> ShadowRunHandoffResponse:
    run = await repo.get_run_by_id(run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"handoff not found for run_id={run_id}")

    out = await repo.get_output_by_run_id(run_id)
    metadata = out.provider_metadata if out is not None else None
    quality = (metadata or {}).get("quality") or {}
    target_profile = _target_profile_from_metadata(getattr(run, "metadata_json", None))
    contract = (
        _recommendation_contract_for_output(out, target_profile=target_profile)[1]
        if out is not None
        else {
            "final_rating": None,
            "decision_markdown": None,
            "recommendation_status": "not_assessed",
            "invalidated_by_quality_gate": False,
            "original_final_rating": None,
        "invalidating_findings": [],
        }
    )
    precedents = await _precedent_matches_for_run(run_id, repo, limit=3)
    provider = (metadata or {}).get("provider") or run.provider
    model_name = (metadata or {}).get("model") or run.model
    deep_model = (metadata or {}).get("deep_model")
    quick_model = (metadata or {}).get("quick_model")

    return ShadowRunHandoffResponse(
        run_id=run.id,
        ticker=run.ticker,
        trade_date=run.trade_date,
        selected_analysts=run.selected_analysts,
        status=_to_api_status(run.status),
        final_rating=contract.get("final_rating"),
        final_decision_markdown=contract.get("decision_markdown"),
        recommendation_status=contract.get("recommendation_status"),
        invalidated_by_quality_gate=bool(contract.get("invalidated_by_quality_gate")),
        original_final_rating=contract.get("original_final_rating"),
        invalidating_findings=contract.get("invalidating_findings") or [],
        state_log_dir=out.state_log_dir if out is not None else None,
        memory_log_path=out.memory_log_path if out is not None else None,
        provider=provider,
        model_name=model_name,
        deep_model=deep_model,
        quick_model=quick_model,
        provider_metadata=metadata,
        quality_status=quality.get("status"),
        quality_findings=quality.get("findings") or [],
        source_summary=quality.get("source_summary"),
        recommendation_audit=quality.get("recommendation_audit"),
        telemetry_summary=(metadata or {}).get("telemetry"),
        target_profile=target_profile,
        precedent_summary={
            "precedent_count": len(precedents),
            "precedents": [_precedent_item(match).model_dump() for match in precedents],
        },
    )


@router.get("/{run_id}/report.md", response_class=PlainTextResponse)
async def get_shadow_run_report_markdown(
    run_id: UUID,
    repo: ShadowRunRepository = Depends(get_shadow_run_repository),
) -> PlainTextResponse:
    run = await repo.get_run_by_id(run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"report not found for run_id={run_id}")
    if not _is_terminal_status(run.status):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="report is available after run completion")

    events = await repo.get_events_by_run_id(run_id)
    artifacts = await repo.get_artifacts_by_run_id(run_id)
    output = await repo.get_output_by_run_id(run_id)
    evaluations = []
    if hasattr(repo, "list_evaluation_runs"):
        evaluations = await repo.list_evaluation_runs(shadow_run_id=run_id, limit=5, offset=0)
    state = load_state_from_artifacts(artifacts, trade_date=run.trade_date)
    markdown = build_shadow_run_markdown_report(
        run=run,
        output=output,
        events=events,
        artifacts=artifacts,
        state=state,
        evaluations=evaluations,
    )
    path = save_shadow_run_markdown_report(
        markdown=markdown,
        path=report_output_path(run=run, output_root=Path("output")),
    )
    return PlainTextResponse(
        markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"X-Report-Path": str(path)},
    )


@router.get("/{run_id}/precedents", response_model=PrecedentListResponse)
async def get_shadow_run_precedents(
    run_id: UUID,
    limit: int = Query(default=10, ge=1, le=50),
    repo: ShadowRunRepository = Depends(get_shadow_run_repository),
) -> PrecedentListResponse:
    run = await repo.get_run_by_id(run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"precedents not found for run_id={run_id}")
    matches = await _precedent_matches_for_run(run_id, repo, limit=limit)
    return PrecedentListResponse(
        query_run_id=run_id,
        query_ticker=run.ticker,
        query_trade_date=run.trade_date,
        precedents=[_precedent_item(match) for match in matches],
    )
