"""Pydantic schemas for the FastAPI service.

Reuses ``gui.brief.Brief`` and ``gui.brief.Trigger`` directly (single
source of truth for the brief shape). Everything else is defined here
so the API surface is stable independent of GUI changes.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from gui.brief import Brief, Trigger  # noqa: F401  (re-exported)


# ---------------------------------------------------------------------------
# Run lifecycle
# ---------------------------------------------------------------------------

class RunCreateRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=32)
    trade_date: str = Field(description="YYYY-MM-DD")
    llm_provider: str = "openai"
    deep_think_llm: str
    quick_think_llm: str
    backend_url: Optional[str] = None
    max_debate_rounds: int = 1
    max_risk_discuss_rounds: int = 1
    data_vendors: Dict[str, str] = Field(
        default_factory=lambda: {
            "core_stock_apis": "yfinance",
            "technical_indicators": "yfinance",
            "fundamental_data": "yfinance",
            "news_data": "yfinance",
        }
    )


class RunSummary(BaseModel):
    """One row of the runs table — what the History page lists."""
    run_id: str
    ticker: str
    trade_date: str
    provider: Optional[str] = None
    deep_model: Optional[str] = None
    quick_model: Optional[str] = None
    debate_rounds: Optional[int] = None
    risk_rounds: Optional[int] = None
    status: str
    decision: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    llm_calls: int = 0
    tool_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    log_path: Optional[str] = None
    error_message: Optional[str] = None
    error_log_path: Optional[str] = None


class RunDetail(RunSummary):
    """Full run state for the per-run drilldown view."""
    state: Dict[str, Any] = Field(default_factory=dict)
    tool_trace: List[Dict[str, Any]] = Field(default_factory=list)


class RunEvent(BaseModel):
    """Server-sent event over the WebSocket while a run streams."""
    type: str  # start | section | debate | risk | chunk | tool_start | tool_end | stats | warning | done | error
    data: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------

class NoteCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1)
    ticker: Optional[str] = None
    run_id: Optional[str] = None
    tags: Optional[str] = None


class NoteUpdateRequest(BaseModel):
    title: str
    body: str
    tags: Optional[str] = None


class Note(BaseModel):
    id: int
    title: str
    body: str
    ticker: Optional[str] = None
    run_id: Optional[str] = None
    tags: Optional[str] = None
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    id: int
    run_id: str
    role: str  # user | assistant
    content: str
    created_at: str
    model: Optional[str] = None


class ChatAskRequest(BaseModel):
    question: str = Field(min_length=1)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

class ProviderKey(BaseModel):
    provider: str
    env_name: str
    label: str
    set_in_env: bool
    set_in_config: bool


class SettingsResponse(BaseModel):
    api_keys: List[ProviderKey]
    defaults: Dict[str, Any]
    config_path: str


class SettingsUpdateRequest(BaseModel):
    api_keys: Optional[Dict[str, str]] = None  # env_name -> value (empty value clears)
    defaults: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Memory log
# ---------------------------------------------------------------------------

class MemoryEntry(BaseModel):
    raw: str
    resolved: bool


class MemoryResponse(BaseModel):
    path: str
    entries: List[MemoryEntry]
    total: int
    resolved_count: int
    pending_count: int


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

class ChartPoint(BaseModel):
    date: str
    values: Dict[str, float]


class ChartComparisonResponse(BaseModel):
    ticker: str
    trade_date: str
    benchmarks: List[str]
    points: List[ChartPoint]
    realised_returns: Optional[List[Dict[str, str]]] = None


# ---------------------------------------------------------------------------
# Briefs
# ---------------------------------------------------------------------------

class BriefResponse(BaseModel):
    run_id: str
    brief: Optional[Brief] = None
    cached: bool
