from __future__ import annotations

import datetime as dt
import json
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Literal, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.llm_clients.validators import VALID_MODELS

load_dotenv()

APP_TITLE = "TradingAgents API"
ANALYST_ORDER = ["market", "social", "news", "fundamentals"]
PROVIDER_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "google": "https://generativelanguage.googleapis.com/v1",
    "anthropic": "https://api.anthropic.com/",
    "xai": "https://api.x.ai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "ollama": "http://localhost:11434/v1",
}


class AnalysisRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=12)
    analysis_date: str = Field(default_factory=lambda: dt.date.today().isoformat())
    analysts: List[str] = Field(default_factory=lambda: ANALYST_ORDER.copy())
    research_depth: Literal[1, 3, 5] = 1
    llm_provider: str = "google"
    quick_think_llm: Optional[str] = None
    deep_think_llm: Optional[str] = None
    backend_url: Optional[str] = None
    google_thinking_level: Optional[str] = "high"
    openai_reasoning_effort: Optional[str] = None

    @field_validator("ticker")
    @classmethod
    def validate_ticker(cls, value: str) -> str:
        ticker = value.strip().upper()
        if not ticker:
            raise ValueError("ticker cannot be empty")
        return ticker

    @field_validator("analysis_date")
    @classmethod
    def validate_date(cls, value: str) -> str:
        try:
            dt.date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("analysis_date must be YYYY-MM-DD") from exc
        return value

    @field_validator("analysts")
    @classmethod
    def validate_analysts(cls, value: List[str]) -> List[str]:
        normalized = [item.strip().lower() for item in value if item.strip()]
        if not normalized:
            raise ValueError("analysts must include at least one analyst")
        invalid = [item for item in normalized if item not in ANALYST_ORDER]
        if invalid:
            raise ValueError(f"invalid analysts: {', '.join(invalid)}")
        return normalized

    @field_validator("llm_provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        provider = value.strip().lower()
        if provider not in PROVIDER_BASE_URLS:
            raise ValueError(f"unsupported provider: {provider}")
        return provider


class AnalysisJob(BaseModel):
    id: str
    status: Literal["queued", "running", "completed", "failed"]
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    request: AnalysisRequest
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


app = FastAPI(title=APP_TITLE, version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_jobs_lock = threading.Lock()
_jobs: Dict[str, AnalysisJob] = {}
_executor = ThreadPoolExecutor(max_workers=2)


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def _default_model(provider: str) -> str:
    models = VALID_MODELS.get(provider)
    if models:
        return models[0]
    if provider == "ollama":
        return "qwen3:latest"
    return "gpt-5-mini"


def _build_config(request: AnalysisRequest) -> Dict[str, Any]:
    config = DEFAULT_CONFIG.copy()
    config["max_debate_rounds"] = request.research_depth
    config["max_risk_discuss_rounds"] = request.research_depth
    config["llm_provider"] = request.llm_provider
    config["backend_url"] = request.backend_url or PROVIDER_BASE_URLS[request.llm_provider]
    config["quick_think_llm"] = request.quick_think_llm or _default_model(request.llm_provider)
    config["deep_think_llm"] = request.deep_think_llm or _default_model(request.llm_provider)
    config["google_thinking_level"] = request.google_thinking_level
    config["openai_reasoning_effort"] = request.openai_reasoning_effort
    return config


def _run_job(job_id: str) -> None:
    with _jobs_lock:
        job = _jobs[job_id]
        job.status = "running"
        job.started_at = dt.datetime.utcnow().isoformat() + "Z"

    try:
        config = _build_config(job.request)
        selected_analysts = [a for a in ANALYST_ORDER if a in job.request.analysts]
        graph = TradingAgentsGraph(
            selected_analysts=selected_analysts,
            debug=False,
            config=config,
        )
        final_state, decision = graph.propagate(
            job.request.ticker,
            job.request.analysis_date,
        )

        result = {
            "ticker": job.request.ticker,
            "analysis_date": job.request.analysis_date,
            "decision": decision,
            "final_trade_decision": _json_safe(final_state.get("final_trade_decision")),
            "investment_plan": _json_safe(final_state.get("investment_plan")),
            "reports": {
                "market": _json_safe(final_state.get("market_report")),
                "sentiment": _json_safe(final_state.get("sentiment_report")),
                "news": _json_safe(final_state.get("news_report")),
                "fundamentals": _json_safe(final_state.get("fundamentals_report")),
                "trader": _json_safe(final_state.get("trader_investment_plan")),
            },
        }

        with _jobs_lock:
            job.status = "completed"
            job.completed_at = dt.datetime.utcnow().isoformat() + "Z"
            job.result = result
            job.error = None
    except Exception:
        with _jobs_lock:
            job.status = "failed"
            job.completed_at = dt.datetime.utcnow().isoformat() + "Z"
            job.error = traceback.format_exc(limit=6)


@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "service": APP_TITLE}


@app.get("/api/options")
def options() -> Dict[str, Any]:
    return {
        "providers": [
            {
                "id": provider,
                "base_url": base_url,
                "models": VALID_MODELS.get(provider, []),
            }
            for provider, base_url in PROVIDER_BASE_URLS.items()
        ],
        "analysts": ANALYST_ORDER,
        "research_depths": [1, 3, 5],
    }


@app.post("/api/analysis/jobs", response_model=AnalysisJob)
def create_analysis_job(request: AnalysisRequest) -> AnalysisJob:
    job_id = str(uuid.uuid4())
    job = AnalysisJob(
        id=job_id,
        status="queued",
        created_at=dt.datetime.utcnow().isoformat() + "Z",
        request=request,
    )
    with _jobs_lock:
        _jobs[job_id] = job

    _executor.submit(_run_job, job_id)
    return job


@app.get("/api/analysis/jobs/{job_id}", response_model=AnalysisJob)
def get_analysis_job(job_id: str) -> AnalysisJob:
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job