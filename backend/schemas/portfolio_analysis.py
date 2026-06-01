from datetime import datetime
from pydantic import BaseModel, Field


class MultiTickerRunRequest(BaseModel):
    tickers: list[str] = Field(..., min_length=2, max_length=10)
    trade_date: str  # YYYY-MM-DD
    asset_type: str = "stock"


class MultiTickerRunResponse(BaseModel):
    task_id: str
    tickers: list[str]
    trade_date: str
    message: str = "Portfolio analysis started"


class MultiTickerListItem(BaseModel):
    id: int
    tickers: list[str]
    trade_date: str
    asset_type: str
    triggered_by: str
    created_at: datetime

    class Config:
        from_attributes = True


class MultiTickerResultRead(BaseModel):
    id: int
    tickers: list[str]
    trade_date: str
    asset_type: str
    analysis_ids: list[int]
    super_portfolio_report: str
    triggered_by: str
    created_at: datetime

    class Config:
        from_attributes = True
