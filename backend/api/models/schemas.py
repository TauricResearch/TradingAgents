from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime
from enum import Enum


class AnalystType(str, Enum):
    MARKET = "market"
    SOCIAL = "social"
    NEWS = "news"
    FUNDAMENTALS = "fundamentals"


class LLMProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    OPENROUTER = "openrouter"
    OLLAMA = "ollama"


class AnalysisRequest(BaseModel):
    ticker: str = Field(..., description="Stock ticker symbol")
    analysis_date: str = Field(..., description="Analysis date in YYYY-MM-DD format")
    analysts: List[AnalystType] = Field(
        default=[AnalystType.MARKET, AnalystType.SOCIAL, AnalystType.NEWS, AnalystType.FUNDAMENTALS],
        description="List of analysts to include"
    )
    research_depth: int = Field(default=1, ge=1, le=10, description="Number of debate rounds")
    llm_provider: LLMProvider = Field(default=LLMProvider.OPENAI, description="LLM provider")
    backend_url: str = Field(default="https://api.openai.com/v1", description="Backend API URL")
    quick_think_llm: str = Field(default="gpt-4o-mini", description="Quick thinking LLM model")
    deep_think_llm: str = Field(default="o4-mini", description="Deep thinking LLM model")
    data_vendors: Optional[Dict[str, str]] = Field(
        default=None,
        description="Data vendor configuration"
    )


class AgentStatus(BaseModel):
    agent: str
    status: Literal["pending", "in_progress", "completed", "error"]
    team: Optional[str] = None


class MessageUpdate(BaseModel):
    timestamp: str
    type: str
    content: str


class ToolCallUpdate(BaseModel):
    timestamp: str
    tool_name: str
    args: Dict[str, Any]


class ReportSection(BaseModel):
    section_name: str
    content: str
    updated_at: str


class AnalysisStatus(BaseModel):
    analysis_id: str
    status: Literal["pending", "running", "completed", "error"]
    ticker: str
    analysis_date: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None


class StreamUpdate(BaseModel):
    type: Literal[
        "status",
        "message",
        "tool_call",
        "report",
        "agent_status",
        "debate_update",
        "risk_debate_update",
        "final_decision"
    ]
    data: Dict[str, Any]
    timestamp: str


class InvestmentDebateState(BaseModel):
    bull_history: Optional[str] = None
    bear_history: Optional[str] = None
    judge_decision: Optional[str] = None
    count: int = 0


class RiskDebateState(BaseModel):
    risky_history: Optional[str] = None
    safe_history: Optional[str] = None
    neutral_history: Optional[str] = None
    current_risky_response: Optional[str] = None
    current_safe_response: Optional[str] = None
    current_neutral_response: Optional[str] = None
    judge_decision: Optional[str] = None
    count: int = 0


class AnalysisResults(BaseModel):
    analysis_id: str
    ticker: str
    analysis_date: str
    market_report: Optional[str] = None
    sentiment_report: Optional[str] = None
    news_report: Optional[str] = None
    fundamentals_report: Optional[str] = None
    investment_debate_state: Optional[InvestmentDebateState] = None
    trader_investment_plan: Optional[str] = None
    risk_debate_state: Optional[RiskDebateState] = None
    final_trade_decision: Optional[str] = None
    processed_signal: Optional[str] = None
    completed_at: str


class HistoricalAnalysisSummary(BaseModel):
    ticker: str
    analysis_date: str
    completed_at: Optional[str] = None
    has_results: bool = False


class ConfigPreset(BaseModel):
    name: str
    description: Optional[str] = None
    config: Dict[str, Any]
    created_at: str

