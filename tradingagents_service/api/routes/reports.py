from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Query

from tradingagents_service.reporting import list_generated_markdown_reports
from tradingagents_service.schemas.reports import ReportListResponse

router = APIRouter(prefix="/v1/reports", tags=["reports"])

REPORT_OUTPUT_ROOT = Path("output")


@router.get("", response_model=ReportListResponse)
async def list_reports(limit: int = Query(default=100, ge=1, le=500)) -> ReportListResponse:
    return ReportListResponse(
        reports=list_generated_markdown_reports(output_root=REPORT_OUTPUT_ROOT, limit=limit)
    )
