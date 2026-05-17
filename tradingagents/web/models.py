"""Models shared by the TradingAgents web console and runner."""

from __future__ import annotations

import datetime as dt
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from tradingagents.default_config import DEFAULT_CONFIG


ANALYST_ORDER = ["market", "social", "news", "fundamentals"]
ANALYST_LABELS = {
    "market": "Market Analyst",
    "social": "Social Analyst",
    "news": "News Analyst",
    "fundamentals": "Fundamentals Analyst",
}


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class AnalysisRequest:
    ticker: str
    analysis_date: str
    output_language: str
    analysts: List[str]
    research_depth: int
    llm_provider: str
    backend_url: Optional[str]
    quick_think_llm: str
    deep_think_llm: str
    google_thinking_level: Optional[str] = None
    openai_reasoning_effort: Optional[str] = None
    anthropic_effort: Optional[str] = None
    deepseek_thinking: Optional[str] = None
    checkpoint: bool = False

    def normalized_analysts(self) -> List[str]:
        selected = {analyst.lower() for analyst in self.analysts}
        return [analyst for analyst in ANALYST_ORDER if analyst in selected]

    def to_config(self) -> Dict[str, Any]:
        config = DEFAULT_CONFIG.copy()
        config["max_debate_rounds"] = self.research_depth
        config["max_risk_discuss_rounds"] = self.research_depth
        config["quick_think_llm"] = self.quick_think_llm
        config["deep_think_llm"] = self.deep_think_llm
        config["backend_url"] = self.backend_url
        config["llm_provider"] = self.llm_provider.lower()
        config["google_thinking_level"] = self.google_thinking_level
        config["openai_reasoning_effort"] = self.openai_reasoning_effort
        config["anthropic_effort"] = self.anthropic_effort
        if self.deepseek_thinking:
            config["deepseek_thinking"] = self.deepseek_thinking
        config["output_language"] = self.output_language
        config["checkpoint_enabled"] = self.checkpoint
        return config

    def to_cache_entry(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "analysis_date": self.analysis_date,
            "output_language": self.output_language,
            "analysts": list(self.analysts),
            "research_depth": self.research_depth,
            "llm_provider": self.llm_provider,
            "backend_url": self.backend_url,
            "quick_think_llm": self.quick_think_llm,
            "deep_think_llm": self.deep_think_llm,
            "google_thinking_level": self.google_thinking_level,
            "openai_reasoning_effort": self.openai_reasoning_effort,
            "anthropic_effort": self.anthropic_effort,
            "deepseek_thinking": self.deepseek_thinking,
            "checkpoint": self.checkpoint,
        }

    @classmethod
    def from_cache_entry(cls, data: Dict[str, Any]) -> "AnalysisRequest":
        return cls(
            ticker=str(data.get("ticker", "SPY")),
            analysis_date=str(data.get("analysis_date", dt.date.today().strftime("%Y-%m-%d"))),
            output_language=str(data.get("output_language", "English")),
            analysts=list(data.get("analysts", ANALYST_ORDER)),
            research_depth=int(data.get("research_depth", 1)),
            llm_provider=str(data.get("llm_provider", "openai")),
            backend_url=data.get("backend_url"),
            quick_think_llm=str(data.get("quick_think_llm", "gpt-5.4-mini")),
            deep_think_llm=str(data.get("deep_think_llm", "gpt-5.4")),
            google_thinking_level=data.get("google_thinking_level"),
            openai_reasoning_effort=data.get("openai_reasoning_effort"),
            anthropic_effort=data.get("anthropic_effort"),
            deepseek_thinking=data.get("deepseek_thinking"),
            checkpoint=bool(data.get("checkpoint", False)),
        )


@dataclass
class AnalysisMessage:
    timestamp: str
    message_type: str
    content: str


@dataclass
class ToolCallRecord:
    timestamp: str
    tool_name: str
    args: Any


@dataclass
class AnalysisSnapshot:
    agent_status: Dict[str, str] = field(default_factory=dict)
    report_sections: Dict[str, Optional[str]] = field(default_factory=dict)
    messages: List[AnalysisMessage] = field(default_factory=list)
    tool_calls: List[ToolCallRecord] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)
    final_state: Optional[Dict[str, Any]] = None
    decision: Optional[Any] = None
    report_path: Optional[str] = None


@dataclass
class AnalysisJob:
    request: AnalysisRequest
    job_id: str = field(default_factory=lambda: uuid4().hex[:12])
    status: JobStatus = JobStatus.QUEUED
    created_at: dt.datetime = field(default_factory=dt.datetime.now)
    started_at: Optional[dt.datetime] = None
    finished_at: Optional[dt.datetime] = None
    error: Optional[str] = None
    snapshot: AnalysisSnapshot = field(default_factory=AnalysisSnapshot)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    def mark_running(self) -> None:
        with self._lock:
            self.status = JobStatus.RUNNING
            self.started_at = dt.datetime.now()

    def mark_completed(self) -> None:
        with self._lock:
            self.status = JobStatus.COMPLETED
            self.finished_at = dt.datetime.now()

    def mark_failed(self, error: str) -> None:
        with self._lock:
            self.status = JobStatus.FAILED
            self.error = error
            self.finished_at = dt.datetime.now()

    def mark_cancelled(self) -> bool:
        with self._lock:
            if self.status != JobStatus.QUEUED:
                return False
            self.status = JobStatus.CANCELLED
            self.finished_at = dt.datetime.now()
            return True

    def update_snapshot(self, snapshot: AnalysisSnapshot) -> None:
        with self._lock:
            self.snapshot = snapshot

    def view(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "job_id": self.job_id,
                "status": self.status.value,
                "created_at": self.created_at,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "error": self.error,
                "request": self.request,
                "snapshot": self.snapshot,
            }
