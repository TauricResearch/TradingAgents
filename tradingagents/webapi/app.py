from __future__ import annotations

import json
import os
from typing import Any, Dict

from dotenv import load_dotenv
from fastapi import Cookie, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse

from .schemas import AnalysisRequest, ApiKeyPayload, AuthStatus, LoginRequest, SettingsPayload
from .service import (
    build_effective_config,
    create_run_summary,
    iter_research_events,
    list_model_catalog,
    now_iso,
    resolve_company_profile,
    search_company_profiles,
)
from .store import SQLiteWebStore

load_dotenv()
load_dotenv(".env.enterprise", override=False)

app = FastAPI(title="TradingAgents Web API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STORE = SQLiteWebStore()
STORE.apply_api_keys_to_env()
AUTH_COOKIE = "tradingagents_session"
AUTH_COOKIE_VALUE = "local-session"


def build_auth_status(session: str | None = None) -> AuthStatus:
    logged_in = session == AUTH_COOKIE_VALUE
    return AuthStatus(logged_in=logged_in, username="admin" if logged_in else None)


@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/api/auth/status", response_model=AuthStatus)
def auth_status(tradingagents_session: str | None = Cookie(default=None)) -> AuthStatus:
    return build_auth_status(tradingagents_session)


@app.post("/api/auth/login", response_model=AuthStatus)
def login(payload: LoginRequest, response: Response) -> AuthStatus:
    expected_user = os.getenv("TRADINGAGENTS_WEB_USER", "admin")
    expected_password = os.getenv("TRADINGAGENTS_WEB_PASSWORD", "admin")
    if payload.username != expected_user or payload.password != expected_password:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    response.set_cookie(
        AUTH_COOKIE,
        AUTH_COOKIE_VALUE,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
    )
    return AuthStatus(logged_in=True, username=payload.username)


@app.post("/api/auth/logout", response_model=AuthStatus)
def logout(response: Response) -> AuthStatus:
    response.delete_cookie(AUTH_COOKIE)
    return AuthStatus(logged_in=False)


@app.get("/api/models")
def models() -> Dict[str, Any]:
    return {"providers": list_model_catalog()}


@app.get("/api/companies/{ticker}")
def get_company_name(ticker: str) -> Dict[str, Any]:
    cleaned = ticker.strip().upper()
    if not cleaned:
        raise HTTPException(status_code=400, detail="Ticker is required")
    return resolve_company_profile(cleaned)


@app.get("/api/companies")
def search_companies(q: str = "") -> Dict[str, Any]:
    return {"items": search_company_profiles(q)}


@app.get("/api/settings")
def get_settings() -> Dict[str, Any]:
    settings = STORE.get_settings()
    return {
        "settings": settings.model_dump(),
        "effective_config": build_effective_config(settings),
        "api_keys": STORE.get_masked_api_keys(),
    }


@app.put("/api/settings")
def update_settings(payload: SettingsPayload) -> Dict[str, Any]:
    STORE.save_settings(payload)
    return {"settings": payload.model_dump()}


@app.put("/api/api-keys/{provider}")
def update_api_key(provider: str, payload: ApiKeyPayload) -> Dict[str, str]:
    try:
        return STORE.save_api_key(provider, payload.value)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}") from exc


@app.get("/api/runs")
def list_runs() -> Dict[str, Any]:
    return {"runs": STORE.list_runs()}


@app.post("/api/runs")
def create_run(payload: AnalysisRequest) -> Dict[str, Any]:
    profile = resolve_company_profile(payload.ticker)
    updates: Dict[str, Any] = {}
    if profile.get("ticker"):
        updates["ticker"] = profile["ticker"]
    if not payload.company_name and profile.get("company_name"):
        updates["company_name"] = profile["company_name"]
    if updates:
        payload = payload.model_copy(update=updates)
    summary = create_run_summary(payload)
    STORE.save_run(summary, payload)
    return {"run": summary}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> Dict[str, Any]:
    run = STORE.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"run": run, "events": STORE.get_events(run_id)}


@app.delete("/api/runs/{run_id}")
def delete_run(run_id: str) -> Dict[str, Any]:
    if not STORE.delete_run(run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    return {"deleted": True, "id": run_id}


def export_run_markdown(run: Dict[str, Any], events: list[Dict[str, Any]]) -> str:
    company = run.get("company_name") or "未填写公司名称"
    lines = [
        f"# {run.get('ticker')} 研究报告",
        "",
        f"- 公司名称：{company}",
        f"- 股票代码：{run.get('ticker')}",
        f"- 分析日期：{run.get('analysis_date')}",
        f"- 状态：{run.get('status')}",
        f"- 结论：{run.get('decision') or '暂无'}",
        "",
        "## 完整对话与事件",
    ]
    for event in events:
        event_type = event.get("type")
        agent = event.get("agent") or "系统"
        content = event.get("content") or ""
        lines.extend(
            [
                "",
                f"### {event.get('createdAt')} · {agent} · {event_type}",
                "",
                content if content else json.dumps(event.get("payload") or {}, ensure_ascii=False, indent=2),
            ]
        )
    return "\n".join(lines).strip() + "\n"


@app.get("/api/runs/{run_id}/export", response_class=PlainTextResponse)
def export_run(run_id: str) -> PlainTextResponse:
    run = STORE.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    content = export_run_markdown(run, STORE.get_events(run_id))
    filename = f"{run.get('ticker', 'run')}-{run.get('analysis_date', 'report')}.md"
    return PlainTextResponse(
        content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/runs/{run_id}/events")
def stream_run_events(run_id: str, ticker: str = "NVDA") -> StreamingResponse:
    run = STORE.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    request = STORE.get_request(run_id) or AnalysisRequest(
        ticker=run.get("ticker") or ticker,
        company_name=run.get("company_name"),
        analysis_date=run.get("analysis_date"),
    )

    def generate():
        STORE.update_run(run_id, status="running", updated_at=now_iso())
        for event in iter_research_events(run_id, request, STORE.get_settings()):
            STORE.append_event(run_id, event)
            updates: Dict[str, Any] = {}
            if event["type"] == "decision":
                updates["decision"] = event["content"]
            if event["type"] == "run_status" and event["status"]:
                updates["status"] = event["status"]
                updates["updated_at"] = event["createdAt"]
            STORE.update_run(run_id, **updates)
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        yield "event: close\ndata: {}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
