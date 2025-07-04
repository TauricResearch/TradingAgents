from datetime import datetime,date
from typing import TYPE_CHECKING
from sqlmodel import SQLModel, Field, JSON, Relationship
import enum
from sqlalchemy import Column

# TYPE_CHECKING을 사용해서 circular import 방지
if TYPE_CHECKING:
    from member.infra.db_models.member import Member

class AnalysisStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Analysis(SQLModel, table=True):
    __tablename__ = "analyses"
    id: str = Field(default=None, max_length=36, primary_key=True)
    
    # 기본 분석 설정 정보
    ticker: str
    analysis_date: date
    analysts_selected: list[str] = Field(sa_column=Column(JSON))
    research_depth: int
    llm_provider: str
    backend_url: str
    shallow_thinker: str
    deep_thinker: str
    status: AnalysisStatus = Field(default=AnalysisStatus.PENDING)
    
    # 개별 분석가 리포트들
    market_report: str | None = Field(default=None, description="Market Analyst 리포트")
    sentiment_report: str | None = Field(default=None, description="Social Analyst 리포트") 
    news_report: str | None = Field(default=None, description="News Analyst 리포트")
    fundamentals_report: str | None = Field(default=None, description="Fundamentals Analyst 리포트")
    
    # 팀별 의사결정 과정
    investment_debate_state: dict | None = Field(default=None, sa_column=Column(JSON), description="Research Team 토론 과정")
    trader_investment_plan: str | None = Field(default=None, description="Trading Team 계획")
    risk_debate_state: dict | None = Field(default=None, sa_column=Column(JSON), description="Risk Management Team 토론 과정")
    
    # 최종 결과물
    final_trade_decision: str | None = Field(default=None, description="최종 거래 결정")
    final_report: str | None = Field(default=None, description="전체 통합 리포트")
    
    # 실행 결과 정보
    error_message: str | None = None
    completed_at: datetime | None = None
    created_at : datetime = Field(nullable=False)
    updated_at : datetime = Field(nullable=False)

    # Foreign Key와 Relationship 설정
    member_id: str = Field(foreign_key="members.id")
    member: "Member" = Relationship(back_populates="analyses")