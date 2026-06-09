"""Pydantic request/response models — the frozen API contract.

Frontend and the parallel backend routers are built against these shapes.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


# ── auth ──
class OtpRequest(BaseModel):
    email: str


class OtpVerify(BaseModel):
    email: str
    code: str


class Me(BaseModel):
    email: str


class OkMessage(BaseModel):
    ok: bool
    message: str = ""


# ── meta ──
class ResolveResult(BaseModel):
    ticker: str
    message: str


class ProviderInfo(BaseModel):
    models: list[str]
    key_present: bool
    key_env: Optional[str] = None


class Defaults(BaseModel):
    provider: str
    deep_model: str
    quick_model: str
    selected_analysts: list[str]
    max_debate_rounds: int
    max_risk_discuss_rounds: int
    output_language: str


# ── analysis ──
class AnalysisStartReq(BaseModel):
    ticker: str
    trade_date: str
    provider: str
    deep_model: str
    quick_model: str
    selected_analysts: list[str]
    max_debate_rounds: int = 1
    max_risk_discuss_rounds: int = 1
    output_language: str = "English"
    checkpoint_enabled: bool = False
    user_research: Optional[str] = None


class AnalysisStartResp(BaseModel):
    run_id: str
    resumed: bool = False


class RunSnapshot(BaseModel):
    run_id: str
    status: str  # pending | running | done | error
    chunks: list[dict[str, Any]]
    stats: Optional[dict[str, Any]] = None
    decision: Optional[str] = None
    error: Optional[dict[str, Any]] = None
    started_at: float
    elapsed: float


# ── prefs ──
class Prefs(BaseModel):
    daily_schedule_enabled: bool = False
    tickers: list[str] = []
    telegram_chat_id: str = ""
    selected_analysts: list[str] = ["market"]
    provider: str = "doubao"
    deep_model: str = "doubao-seed-1-6-250615"
    quick_model: str = "doubao-seed-1-6-flash-250828"
    output_language: str = "中文"
    max_debate_rounds: int = 1
    max_risk_discuss_rounds: int = 1


# ── research / history ──
class ResearchItem(BaseModel):
    digest: str
    filename: str
    ticker: str
    summary: str = ""
    uploaded_at: Optional[str] = None


class HistoryEntry(BaseModel):
    ticker: str
    trade_date: str
    decision: str
    pending: bool
    raw_text: str = ""


class TelegramTestReq(BaseModel):
    chat_id: str
