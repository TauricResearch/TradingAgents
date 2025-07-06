from pydantic import BaseModel
from datetime import datetime
from typing import List, Dict

class Analysis(BaseModel):
    id: str | None = None
    member_id: str
    ticker: str
    analysis_date: str
    analysts_selected: List[str] = []
    research_depth: int = 3
    llm_provider: str = "openai"
    backend_url: str = "https://api.openai.com/v1"
    shallow_thinker: str = "gpt-4o-mini"
    deep_thinker: str = "gpt-4o"
    status: str
    
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
    created_at: datetime
    updated_at: datetime