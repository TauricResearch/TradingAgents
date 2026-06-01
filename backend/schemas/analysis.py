from datetime import datetime
from pydantic import BaseModel


class AnalysisRunRequest(BaseModel):
    ticker: str
    trade_date: str  # YYYY-MM-DD
    asset_type: str = "stock"


class AnalysisRunResponse(BaseModel):
    task_id: str
    ticker: str
    trade_date: str
    message: str = "Analysis started"


class AnalysisResultRead(BaseModel):
    id: int
    ticker: str
    trade_date: str
    asset_type: str
    signal: str | None
    market_report: str
    sentiment_report: str
    news_report: str
    fundamentals_report: str
    macro_report: str
    options_report: str
    quant_report: str
    earnings_report: str
    review_report: str
    investment_plan: str
    trader_plan: str
    final_decision: str
    llm_calls: int
    tool_calls: int
    tokens_in: int
    tokens_out: int
    duration_seconds: float
    triggered_by: str
    created_at: datetime

    class Config:
        from_attributes = True


class AnalysisListItem(BaseModel):
    id: int
    ticker: str
    trade_date: str
    asset_type: str
    signal: str | None
    duration_seconds: float
    triggered_by: str
    created_at: datetime

    class Config:
        from_attributes = True
