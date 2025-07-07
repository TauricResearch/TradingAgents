from pydantic import BaseModel, field_validator
from datetime import datetime, date
from typing import List, Dict, Union
from analysis.infra.db_models.analysis import AnalysisStatus

class Analysis(BaseModel):
    id: str | None = None
    member_id: str | None = None
    ticker: str | None = None
    analysis_date: date | None = None
    analysts_selected: list[str] = []
    research_depth: int = 1
    llm_provider: str = "google"
    backend_url: str = "https://generativelanguage.googleapis.com/v1"
    shallow_thinker: str = "gemini-2.5-flash-lite-preview-06-17"
    deep_thinker: str = "gemini-2.5-flash-lite-preview-06-17"
    status: AnalysisStatus = AnalysisStatus.PENDING
    
    # 개별 분석가 리포트들
    market_report: str | None = None
    sentiment_report: str | None = None
    news_report: str | None = None
    fundamentals_report: str | None = None
    
    # 팀별 의사결정 과정
    investment_debate_state: Dict | None = None
    trader_investment_plan: str | None = None
    risk_debate_state: Dict | None = None
    
    # 최종 결과물
    final_trade_decision: str | None = None
    final_report: str | None = None
    
    # 실행 결과 정보
    error_message: str | None = None
    completed_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None