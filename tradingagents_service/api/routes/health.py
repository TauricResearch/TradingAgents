from fastapi import APIRouter

from tradingagents_service.schemas.shadow_runs import HealthResponse, ReadinessResponse

router = APIRouter(tags=["system"])


@router.get("/healthz", response_model=HealthResponse)
def get_healthz() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/readyz", response_model=ReadinessResponse)
def get_readyz() -> ReadinessResponse:
    return ReadinessResponse(status="ready")
