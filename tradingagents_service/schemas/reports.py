from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ReportItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    ticker: str
    trade_date: date
    path: str
    report_url: str
    bytes: int
    updated_at: datetime


class ReportListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reports: list[ReportItem]
