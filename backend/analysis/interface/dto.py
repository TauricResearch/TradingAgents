from pydantic import BaseModel
from datetime import date
from typing import List
from analysis.infra.db_models.analysis import AnalysisStatus
from enum import Enum

class AnalystType(str, Enum):
    MARKET = "market"
    SOCIAL = "social"
    NEWS = "news"
    FUNDAMENTALS = "fundamentals"

class TradingAnalysisRequest(BaseModel):
    ticker: str
    analysis_date: str
    analysts: List[AnalystType]
    research_depth: int = 3
    llm_provider: str = "openai"
    backend_url: str = "https://api.openai.com/v1"
    shallow_thinker: str = "gpt-4o-mini"
    deep_thinker: str = "gpt-4o"

class AnalysisSessionResponse(BaseModel):
    id : str
    ticker : str
    status : AnalysisStatus

class AnalysisProgressUpdate(BaseModel):
    analysis_id: str
    current_agent: str
    status: str
    progress_percentage: float
    current_report_section: str | None = None
    message: str | None = None

class AnalysisResultResponse(BaseModel):
    id: str
    ticker: str
    analysis_date: str
    status: AnalysisStatus
    market_report: str | None = None
    sentiment_report: str | None = None
    news_report: str | None = None
    fundamentals_report: str | None = None
    investment_debate_state: dict | None = None
    trader_investment_plan: str | None = None
    risk_debate_state: dict | None = None
    final_trade_decision: str | None = None
    final_report: str | None = None
    created_at: str
    completed_at: str | None = None
    error_message: str | None = None