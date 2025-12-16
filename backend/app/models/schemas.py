"""
Pydantic models for request/response schemas
"""
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict, Any, Literal, Union
from datetime import date


class AnalysisRequest(BaseModel):
    """Request model for trading analysis"""
    ticker: str = Field(..., description="Stock ticker symbol (e.g., 'NVDA', 'AAPL')", min_length=1, max_length=10)
    
    # 防呆：自動將股票代碼轉換為大寫
    @field_validator('ticker')
    @classmethod
    def uppercase_ticker(cls, v: str) -> str:
        return v.strip().upper()
    analysis_date: str = Field(..., description="Analysis date in YYYY-MM-DD format")
    analysts: Optional[List[str]] = Field(
        default=["market", "social", "news", "fundamentals"],
        description="List of analysts to include in analysis"
    )
    research_depth: Optional[int] = Field(default=1, ge=1, le=5, description="Research depth (1-5)")
    market_type: Optional[Literal["us", "twse", "tpex"]] = Field(
        default="us",
        description="Market type: 'us' for US stocks, 'twse' for Taiwan TWSE (上市), 'tpex' for Taiwan TPEx/ROTC (上櫃/興櫃)"
    )
    deep_think_llm: Optional[str] = Field(default="gpt-5-mini", description="Deep thinking LLM model")
    quick_think_llm: Optional[str] = Field(default="gpt-5-mini", description="Quick thinking LLM model")
    
    # API Configuration
    openai_api_key: Optional[str] = Field(None, description="OpenAI API Key (optional if set on server)", min_length=0)
    openai_base_url: Optional[str] = Field(
        default="https://api.openai.com/v1",
        description="OpenAI API Base URL (optional, deprecated)"
    )
    quick_think_base_url: Optional[str] = Field(
        default="https://api.openai.com/v1",
        description="Base URL for Quick Thinking Model"
    )
    deep_think_base_url: Optional[str] = Field(
        default="https://api.openai.com/v1",
        description="Base URL for Deep Thinking Model"
    )
    quick_think_api_key: Optional[str] = Field(None, description="API Key for Quick Thinking Model", min_length=0)
    deep_think_api_key: Optional[str] = Field(None, description="API Key for Deep Thinking Model", min_length=0)
    embedding_base_url: Optional[str] = Field(
        default="https://api.openai.com/v1",
        description="Base URL for Embedding Model"
    )
    embedding_api_key: Optional[str] = Field(None, description="API Key for Embedding Model", min_length=0)
    alpha_vantage_api_key: Optional[str] = Field(
        None,
        description="Alpha Vantage API Key (optional, for US stock fundamental data)",
        min_length=0
    )
    finmind_api_key: Optional[str] = Field(
        None,
        description="FinMind API Token (optional, for Taiwan stock data)",
        min_length=0
    )


class PriceData(BaseModel):
    """Stock price data model"""
    Date: str
    Open: float
    High: float
    Low: float
    Close: float
    Volume: int


class PriceStats(BaseModel):
    """Price statistics model"""
    growth_rate: float = Field(..., description="Price growth rate in percentage")
    duration_days: int = Field(..., description="Data duration in days")
    start_date: str
    end_date: str
    start_price: float
    end_price: float


class AnalysisResponse(BaseModel):
    """Response model for trading analysis"""
    status: str = Field(..., description="Analysis status (success, error, processing)")
    ticker: str = Field(..., description="Stock ticker analyzed")
    analysis_date: str = Field(..., description="Date of analysis")
    decision: Optional[Union[str, Dict[str, Any]]] = Field(None, description="Trading decision (string or details dict)")
    reports: Optional[Dict[str, Any]] = Field(None, description="Analysis reports from different teams")
    error: Optional[str] = Field(None, description="Error message if analysis failed")
    price_data: Optional[List[PriceData]] = Field(None, description="Historical price data")
    price_stats: Optional[PriceStats] = Field(None, description="Price statistics")


class ConfigResponse(BaseModel):
    """Response model for configuration options"""
    available_analysts: List[str] = Field(..., description="Available analyst types")
    available_llms: List[str] = Field(..., description="Available LLM models")
    default_config: Dict[str, Any] = Field(..., description="Default configuration values")


class HealthResponse(BaseModel):
    """Response model for health check"""
    status: str = Field(..., description="API health status")
    version: str = Field(..., description="API version")
    timestamp: str = Field(..., description="Current server timestamp")
    redis_connected: bool = Field(False, description="Whether Redis is connected")


class ErrorResponse(BaseModel):
    """Response model for errors"""
    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Detailed error information")
    status_code: int = Field(..., description="HTTP status code")


class Ticker(BaseModel):
    """Ticker information model"""
    symbol: str = Field(..., description="Stock ticker symbol")
    name: str = Field(..., description="Company name")


# Task Management Schemas

class TaskCreatedResponse(BaseModel):
    """Response when a task is created"""
    task_id: str = Field(..., description="Unique task identifier")
    status: Literal["pending"] = Field(default="pending", description="Initial task status")
    message: str = Field(default="Analysis task created successfully", description="Success message")


class TaskStatusResponse(BaseModel):
    """Response for task status query"""
    task_id: str = Field(..., description="Task identifier")
    status: Literal["pending", "running", "completed", "failed"] = Field(..., description="Current task status")
    created_at: str = Field(..., description="Task creation timestamp")
    updated_at: str = Field(..., description="Last update timestamp")
    progress: Optional[str] = Field(None, description="Progress message")
    result: Optional[AnalysisResponse] = Field(None, description="Analysis result (only when completed)")
    error: Optional[str] = Field(None, description="Error message (only when failed)")
    completed_at: Optional[str] = Field(None, description="Completion timestamp")


# Download Schemas

class AnalystReport(BaseModel):
    """Single analyst report for download"""
    analyst_name: str = Field(..., description="Name of the analyst")
    report_key: str = Field(..., description="Key to access report in results")


class DownloadRequest(BaseModel):
    """Request model for downloading analyst reports"""
    ticker: str = Field(..., description="Stock ticker symbol")
    analysis_date: str = Field(..., description="Analysis date in YYYY-MM-DD format")
    analysts: List[str] = Field(..., description="List of analyst keys to download", min_length=1)
    
    # Task-based mode: lookup reports from task
    task_id: Optional[str] = Field(None, description="Task ID of the completed analysis (optional)")
    
    # Direct mode: reports data passed directly (for history/saved reports)
    reports: Optional[Dict[str, Any]] = Field(None, description="Direct reports data (if no task_id)")
    price_data: Optional[List[Dict[str, Any]]] = Field(None, description="Price data for PDF chart")
    price_stats: Optional[Dict[str, Any]] = Field(None, description="Price stats for PDF cover page")
    
    # 防呆：自動將股票代碼轉換為大寫
    @field_validator('ticker')
    @classmethod
    def uppercase_ticker(cls, v: str) -> str:
        return v.strip().upper()

