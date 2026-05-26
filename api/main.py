"""
TradingAgents REST API — FastAPI application.

Endpoints:
  POST   /analyze                Submit a stock analysis request
  GET    /status/{request_id}    Get status of a specific request
  GET    /requests/open          List all pending/running requests
  GET    /requests/closed        List all completed/failed requests
  GET    /analysis/{filename}    Download the detailed analysis text file
  GET    /healthz                Health check
"""
from __future__ import annotations

import asyncio
import datetime
import html
import json
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.responses import RedirectResponse

from api.db import (
    DB_PATH,
    cancel_all_open_requests,
    cancel_request,
    create_batch_schedule,
    create_request,
    delete_batch_schedule,
    get_batch_schedule,
    get_llm_calls_by_provider_between,
    get_llm_usage_by_provider_between,
    get_llm_role_stats_between,
    get_recommendation_history,
    list_due_batch_schedules,
    list_due_pending_requests,
    get_request,
    init_db,
    list_batch_schedules,
    list_requests,
    mark_stale_running_requests,
    update_batch_schedule_config,
    update_batch_schedule_run,
)
from api.schemas import (
    AnalyzeRequest,
    BatchScheduleCreateRequest,
    BatchScheduleItem,
    BatchScheduleListResponse,
    BatchScheduleRerunRequest,
    BatchScheduleUpdateRequest,
    CancelAllResponse,
    CancelResponse,
    EnvVarUpdateRequest,
    EnvVarValueResponse,
    LatestRecommendationResponse,
    RequestListResponse,
    RequestStatus,
    SubmitResponse,
    VaultRefreshResponse,
)
from api.vault import VaultError, refresh_runtime_env_from_vault
from api.worker import ANALYSIS_DIR, get_live_provider_calls, task_queue, worker_loop

_API_VERSION = "1.0.0"
_NUM_WORKERS = 1
_NUM_SCHEDULERS = 1
_SUPPORTED_PROVIDERS = {"ollama", "google", "openrouter"}
_SUPPORTED_BATCH_FREQUENCIES = {"daily", "weekly", "monthly"}
_ROOT_DIR = Path(__file__).resolve().parent.parent
_ENV_FILE = _ROOT_DIR / ".env"
_ENV_NAME_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{1,127}$")
_SCHEDULER_POLL_SECONDS = 30


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _next_midnight_utc_iso(now: Optional[datetime.datetime] = None) -> str:
    current = now or _utc_now()
    next_day = (current + datetime.timedelta(days=1)).date()
    return datetime.datetime.combine(next_day, datetime.time.min, tzinfo=datetime.timezone.utc).isoformat()


def _next_run_utc_iso(frequency: str, from_time: Optional[datetime.datetime] = None) -> str:
    base = from_time or _utc_now()
    f = frequency.lower()
    if f == "daily":
        nxt = base + datetime.timedelta(days=1)
    elif f == "weekly":
        nxt = base + datetime.timedelta(days=7)
    else:
        # Keep scheduling simple and deterministic for monthly cadence.
        nxt = base + datetime.timedelta(days=30)
    return nxt.isoformat()


def _latest_business_date_iso(from_time: Optional[datetime.datetime] = None) -> str:
    """Return latest business date (Mon-Fri) in UTC.

    If current day is Saturday/Sunday, returns the most recent Friday.
    """
    base_date = (from_time or _utc_now()).date()
    weekday = base_date.weekday()  # Mon=0 ... Sun=6
    if weekday == 5:  # Saturday
        base_date = base_date - datetime.timedelta(days=1)
    elif weekday == 6:  # Sunday
        base_date = base_date - datetime.timedelta(days=2)
    return base_date.isoformat()


def _build_status(row: dict, base_url: str) -> RequestStatus:
    analysis_url: Optional[str] = None
    debug_log_url: Optional[str] = None
    agent_recommendations = None
    
    if row.get("analysis_file"):
        analysis_url = f"{base_url}/analysis/{row['analysis_file']}"
    if row.get("status") != "canceled":
        debug_log_url = f"{base_url}/logs/{row['id']}"
    
    # Parse agent_recommendations JSON if present
    if row.get("agent_recommendations"):
        try:
            agent_recommendations = json.loads(row["agent_recommendations"])
        except (json.JSONDecodeError, TypeError):
            agent_recommendations = None
    
    return RequestStatus(
        request_id=row["id"],
        ticker=row["ticker"],
        analysis_date=row["analysis_date"],
        llm_provider=row.get("llm_provider"),
        deep_model=row.get("deep_model"),
        quick_model=row.get("quick_model"),
        status=row["status"],
        submitted_at=row["submitted_at"],
        started_at=row.get("started_at"),
        completed_at=row.get("completed_at"),
        recommendation=row.get("recommendation"),
        llm_calls=row.get("llm_calls"),
        tool_calls=row.get("tool_calls"),
        tokens_in=row.get("tokens_in"),
        tokens_out=row.get("tokens_out"),
        total_tokens=row.get("total_tokens"),
        estimated_cost_usd=row.get("estimated_cost_usd"),
        agent_recommendations=agent_recommendations,
        analysis_url=analysis_url,
        debug_log_url=debug_log_url,
        error_message=row.get("error_message"),
    )


def _build_agent_recommendations(final_state: Optional[dict]) -> dict:
    """Normalize graph output into a UI-friendly agent recommendation payload."""
    if not final_state:
        return {}

    risk_state = final_state.get("risk_debate_state", {}) or {}
    investment_state = final_state.get("investment_debate_state", {}) or {}

    def entry(label: str, weight: int, recommendation) -> dict:
        return {
            "label": label,
            "weight": weight,
            "recommendation": recommendation or "",
        }

    return {
        "market_analyst": entry("Market Analyst", 15, final_state.get("market_report")),
        "fundamentals_analyst": entry("Fundamentals Analyst", 15, final_state.get("fundamentals_report")),
        "news_analyst": entry("News Analyst", 10, final_state.get("news_report")),
        "social_media_analyst": entry("Social Media Analyst", 10, final_state.get("sentiment_report")),
        "bull_researcher": entry("Bull Researcher", 5, investment_state.get("bull_history")),
        "bear_researcher": entry("Bear Researcher", 5, investment_state.get("bear_history")),
        "investment_judge": entry("Investment Judge", 5, investment_state.get("judge_decision")),
        "trader": entry("Trader", 10, final_state.get("trader_investment_plan")),
        "aggressive_analyst": entry("Aggressive Risk Analyst", 5, risk_state.get("aggressive_history")),
        "neutral_analyst": entry("Neutral Risk Analyst", 5, risk_state.get("neutral_history")),
        "conservative_analyst": entry("Conservative Risk Analyst", 5, risk_state.get("conservative_history")),
        "risk_judge": entry("Risk Judge", 5, risk_state.get("judge_decision")),
        "portfolio_manager": entry("Portfolio Manager", 5, final_state.get("final_trade_decision")),
    }


def _validate_env_name(var_name: str) -> str:
    name = (var_name or "").strip().upper()
    if not _ENV_NAME_PATTERN.fullmatch(name):
        raise HTTPException(status_code=400, detail="Invalid env variable name format")
    return name


def _read_env_keys() -> list[str]:
    keys: list[str] = []
    if not _ENV_FILE.exists():
        return keys
    text = _ENV_FILE.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _ = stripped.split("=", 1)
        key_name = key.strip()
        if key_name and _ENV_NAME_PATTERN.fullmatch(key_name):
            keys.append(key_name)
    seen = set()
    unique: list[str] = []
    for key in keys:
        if key in seen:
            continue
        seen.add(key)
        unique.append(key)
    return unique


def _read_env_file_value(var_name: str) -> Optional[str]:
    if not _ENV_FILE.exists():
        return None
    text = _ENV_FILE.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip() == var_name:
            return value
    return None


def _upsert_env_file_value(var_name: str, value: str) -> None:
    lines: list[str] = []
    if _ENV_FILE.exists():
        lines = _ENV_FILE.read_text(encoding="utf-8", errors="replace").splitlines()

    safe_value = value.replace("\r", "").replace("\n", "")
    target_prefix = f"{var_name}="
    replaced = False
    new_lines: list[str] = []
    for line in lines:
        if line.strip().startswith("#") or "=" not in line:
            new_lines.append(line)
            continue
        key, _ = line.split("=", 1)
        if key.strip() == var_name:
            new_lines.append(f"{target_prefix}{safe_value}")
            replaced = True
        else:
            new_lines.append(line)

    if not replaced:
        if new_lines and new_lines[-1].strip() != "":
            new_lines.append("")
        new_lines.append(f"{target_prefix}{safe_value}")

    _ENV_FILE.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def _refresh_vault_keys_and_persist() -> dict:
    summary = refresh_runtime_env_from_vault()
    for key in summary.get("keys", []):
        val = os.getenv(key)
        if val is not None:
            _upsert_env_file_value(key, val)
    return summary


def _build_batch_schedule_item(row: dict, base_url: str) -> BatchScheduleItem:
    latest_request_id = row.get("latest_request_id")
    latest_logs_url: Optional[str] = None
    latest_analysis_url: Optional[str] = None
    if latest_request_id:
        latest_logs_url = f"{base_url}/logs/{latest_request_id}"
    if row.get("latest_analysis_file"):
        latest_analysis_url = f"{base_url}/analysis/{row['latest_analysis_file']}"

    return BatchScheduleItem(
        id=row["id"],
        ticker=row["ticker"],
        llm_provider=row["llm_provider"],
        frequency=row["frequency"],
        next_run_at=row.get("next_run_at"),
        last_schedule_run_at=row.get("last_run_at"),
        latest_recommendation=row.get("latest_recommendation"),
        last_run_at=row.get("latest_completed_at") or row.get("latest_submitted_at"),
        latest_logs_url=latest_logs_url,
        latest_analysis_url=latest_analysis_url,
    )


async def _enqueue_due_pending_requests_once() -> int:
    """Enqueue due pending requests, prioritizing quota-deferred requests first."""
    if task_queue.qsize() > 0:
        return 0
    now_iso = _utc_now().isoformat()
    rows = await list_due_pending_requests(now_iso=now_iso, db_path=DB_PATH)
    for row in rows:
        await task_queue.put((row["id"], row["ticker"], row["analysis_date"]))
    return len(rows)


async def _pending_enqueue_loop() -> None:
    while True:
        await _enqueue_due_pending_requests_once()
        await asyncio.sleep(_SCHEDULER_POLL_SECONDS)


async def _batch_schedule_loop() -> None:
    """Create queued analysis requests for due batch schedules."""
    while True:
        now = _utc_now()
        now_iso = now.isoformat()
        business_date = _latest_business_date_iso(now)
        due_rows = await list_due_batch_schedules(now_iso=now_iso, db_path=DB_PATH)
        for schedule in due_rows:
            req_id = await create_request(
                ticker=schedule["ticker"],
                analysis_date=business_date,
                llm_provider=schedule["llm_provider"],
                available_after=now_iso,
                db_path=DB_PATH,
            )
            await task_queue.put((req_id, schedule["ticker"], business_date))
            await update_batch_schedule_run(
                schedule_id=schedule["id"],
                last_run_at=now_iso,
                next_run_at=_next_run_utc_iso(schedule["frequency"], now),
                db_path=DB_PATH,
            )
        await asyncio.sleep(_SCHEDULER_POLL_SECONDS)


def _wants_html_response(request: Request) -> bool:
    fmt = (request.query_params.get("format") or "").lower()
    pretty = (request.query_params.get("pretty") or "").lower()
    if fmt == "html" or pretty in ("1", "true", "yes"):
        return True
    accept = (request.headers.get("accept") or "").lower()
    return "text/html" in accept and "application/json" not in accept


def _render_closed_requests_html(items: list[RequestStatus]) -> str:
    lines: list[str] = []
    for item in items:
        rec = html.escape(item.recommendation or "-")
        err = html.escape(item.error_message or "-")
        analysis_link = (
            f'<a href="{html.escape(item.analysis_url)}" target="_blank" rel="noopener">analysis</a>'
            if item.analysis_url
            else "-"
        )
        log_link = (
            f'<a href="{html.escape(item.debug_log_url)}" target="_blank" rel="noopener">log</a>'
            if item.debug_log_url
            else "-"
        )
        lines.append(
            f"""
            <article class=\"row\">
                <div class=\"head\">
                    <span class=\"ticker\">{html.escape(item.ticker)}</span>
                    <span class=\"status status-{html.escape(item.status)}\">{html.escape(item.status)}</span>
                </div>
                <div class=\"meta\">request: {html.escape(item.request_id)}</div>
                <div class=\"meta\">analysis date: {html.escape(item.analysis_date)}</div>
                <div class="meta">provider: {html.escape(item.llm_provider or '-')}</div>
                <div class="meta">models (deep / quick): {html.escape(item.deep_model or '-')} / {html.escape(item.quick_model or '-')}</div>
                <div class=\"meta\">submitted: {html.escape(item.submitted_at)}</div>
                <div class=\"meta\">start time: {html.escape(item.started_at or '-')}</div>
                <div class=\"meta\">end time: {html.escape(item.completed_at or '-')}</div>
                <div class="meta">llm calls: {item.llm_calls if item.llm_calls is not None else '-'}</div>
                <div class="meta">tool calls: {item.tool_calls if item.tool_calls is not None else '-'}</div>
                <div class="meta">tokens in/out/total: {item.tokens_in if item.tokens_in is not None else '-'} / {item.tokens_out if item.tokens_out is not None else '-'} / {item.total_tokens if item.total_tokens is not None else '-'}</div>
                <div class="meta">estimated cost (USD): {item.estimated_cost_usd if item.estimated_cost_usd is not None else '-'}</div>
                <div class=\"meta\">recommendation: {rec}</div>
                <div class=\"meta\">error: {err}</div>
                <div class=\"links\">{analysis_link} | {log_link}</div>
            </article>
            """
        )

    body = "\n".join(lines) if lines else "<p class=\"empty\">No closed requests yet.</p>"
    return f"""
<!doctype html>
<html>
<head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>Closed Requests</title>
    <style>
        :root {{ --ink:#10221f; --muted:#44615a; --paper:#f4fbf8; --card:#ffffff; --line:#cfe5dc; --ok:#0f766e; --warn:#b45309; --bad:#b91c1c; }}
        body {{ margin:0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color:var(--ink); background:radial-gradient(circle at 10% 10%, #e6fff6 0%, #f4fbf8 55%, #eef6ff 100%); }}
        .wrap {{ max-width: 980px; margin: 28px auto; padding: 0 14px; }}
        h1 {{ margin: 0 0 14px; font-size: 28px; }}
        .sub {{ color:var(--muted); margin-bottom:14px; }}
        .row {{ display:block; background:var(--card); border:1px solid var(--line); border-radius:12px; padding:12px 14px; margin-bottom:10px; box-shadow: 0 8px 20px rgba(16,34,31,0.07); }}
        .head {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:6px; }}
        .ticker {{ font-size:18px; font-weight:700; letter-spacing:.2px; }}
        .status {{ font-size:12px; font-weight:700; text-transform:uppercase; border-radius:999px; padding:4px 8px; }}
        .status-completed {{ color: #064e3b; background: #d1fae5; }}
        .status-failed {{ color: #7f1d1d; background: #fee2e2; }}
        .status-canceled {{ color: #78350f; background: #ffedd5; }}
        .meta {{ font-size:13px; line-height:1.55; word-break:break-word; }}
        .links {{ margin-top:7px; font-size:13px; }}
        a {{ color:#0f766e; text-decoration:none; font-weight:600; }}
        a:hover {{ text-decoration:underline; }}
        .empty {{ background:var(--card); border:1px dashed var(--line); border-radius:12px; padding:14px; }}
    </style>
</head>
<body>
    <main class=\"wrap\">
        <div style="display:flex;gap:8px;flex-wrap:wrap;justify-content:center;margin:0 0 12px">
            <a href="/ui" style="background:#374151;color:#fff;padding:8px 10px;border-radius:8px;text-decoration:none;font-weight:600">Operations</a>
            <a href="/batching" style="background:#0f766e;color:#fff;padding:8px 10px;border-radius:8px;text-decoration:none;font-weight:600">Batching</a>
            <a href="/completed" style="background:#111827;color:#fff;padding:8px 10px;border-radius:8px;text-decoration:none;font-weight:600">Completed</a>
            <a href="/requests/closed?format=html" style="background:#7c3aed;color:#fff;padding:8px 10px;border-radius:8px;text-decoration:none;font-weight:600">Closed</a>
            <a href="/settings" style="background:#1d4ed8;color:#fff;padding:8px 10px;border-radius:8px;text-decoration:none;font-weight:600">Settings</a>
        </div>
        <h1>Closed Requests</h1>
        <p class=\"sub\">Each request appears on its own line with direct links to analysis and logs.</p>
        {body}
    </main>
</body>
</html>
    """


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        _refresh_vault_keys_and_persist()
    except VaultError as exc:
        # Keep service booting even if Vault is temporarily unavailable.
        print(f"[Vault] startup refresh failed: {exc}")

    await init_db(DB_PATH)
    await mark_stale_running_requests(db_path=DB_PATH)
    await _enqueue_due_pending_requests_once()
    Path(ANALYSIS_DIR).mkdir(parents=True, exist_ok=True)
    # Start worker and scheduler tasks.
    workers = [
        asyncio.create_task(worker_loop(db_path=DB_PATH))
        for _ in range(_NUM_WORKERS)
    ]
    schedulers = [
        asyncio.create_task(_pending_enqueue_loop()),
        *[
            asyncio.create_task(_batch_schedule_loop())
            for _ in range(_NUM_SCHEDULERS)
        ],
    ]
    yield
    # Cancel background tasks on shutdown.
    for w in workers:
        w.cancel()
    for s in schedulers:
        s.cancel()


app = FastAPI(
    title="TradingAgents API",
    description="Submit stock analysis requests and retrieve AI-generated trading recommendations.",
    version=_API_VERSION,
    lifespan=lifespan,
)


_HAS_MCP_SERVER = (_ROOT_DIR / "mcp_server" / "tradingagents_mcp_server.py").exists()


@app.get("/", include_in_schema=False)
async def root_redirect():
    """Redirect browser users to the built-in lightweight UI."""
    return RedirectResponse(url="/ui", status_code=307)


@app.get("/api-definition", response_class=JSONResponse)
async def api_definition():
    """Explicit OpenAPI endpoint alias."""
    return app.openapi()


@app.get("/mcp-server", response_class=JSONResponse)
async def mcp_server_definition():
    """Return MCP server endpoint/usage metadata when MCP server is available."""
    if not _HAS_MCP_SERVER:
        raise HTTPException(status_code=404, detail="MCP server is not available in this deployment")
    return JSONResponse(
        content={
            "name": "tradingagents-api",
            "run_command": "tradingagents-mcp",
            "transport": "stdio",
            "env": {
                "TRADINGAGENTS_API_BASE_URL": "http://localhost:9000",
            },
            "documentation": "Use the tradingagents-mcp command to start the MCP server.",
        }
    )


# ---------------------------------------------------------------------------
# POST /analyze
# ---------------------------------------------------------------------------
@app.post("/analyze", response_model=SubmitResponse, status_code=202)
async def submit_analysis(body: AnalyzeRequest, request: Request):
    """Submit a stock analysis request. Returns a request_id immediately."""
    ticker = body.ticker.strip().upper()
    if not ticker:
        raise HTTPException(status_code=400, detail="ticker must not be empty")

    analysis_date = body.date or datetime.date.today().isoformat()

    # Validate date format and ensure not in the future
    try:
        parsed = datetime.date.fromisoformat(analysis_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
    if parsed > datetime.date.today():
        raise HTTPException(status_code=400, detail="date cannot be in the future")

    llm_provider = (body.llm_provider or "ollama").strip().lower()
    if llm_provider not in _SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=(
                "llm_provider must be one of: "
                + ", ".join(sorted(_SUPPORTED_PROVIDERS))
            ),
        )

    req_id = await create_request(ticker, analysis_date, llm_provider=llm_provider, db_path=DB_PATH)
    await task_queue.put((req_id, ticker, analysis_date))

    return SubmitResponse(
        request_id=req_id,
        ticker=ticker,
        analysis_date=analysis_date,
        llm_provider=llm_provider,
        status="pending",
        submitted_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    )


# ---------------------------------------------------------------------------
# GET /status/{request_id}
# ---------------------------------------------------------------------------
@app.get("/status/{request_id}", response_model=RequestStatus)
async def get_status(request_id: str, request: Request):
    """Get the current status and result of a specific analysis request."""
    row = await get_request(request_id, db_path=DB_PATH)
    if not row:
        raise HTTPException(status_code=404, detail="Request not found")
    base_url = str(request.base_url).rstrip("/")
    return _build_status(row, base_url)


# ---------------------------------------------------------------------------
# GET /requests/open
# ---------------------------------------------------------------------------
@app.get("/requests/open", response_model=RequestListResponse)
async def list_open_requests(request: Request):
    """List all pending and running analysis requests."""
    rows = await list_requests("open", db_path=DB_PATH)
    base_url = str(request.base_url).rstrip("/")
    items = [_build_status(r, base_url) for r in rows]
    return RequestListResponse(total=len(items), requests=items)


# ---------------------------------------------------------------------------
# GET /requests/closed
# ---------------------------------------------------------------------------
@app.get("/requests/closed", response_model=RequestListResponse)
async def list_closed_requests(request: Request):
    """List all completed and failed analysis requests with recommendations."""
    rows = await list_requests("closed", db_path=DB_PATH)
    base_url = str(request.base_url).rstrip("/")
    items = [_build_status(r, base_url) for r in rows]
    if _wants_html_response(request):
        return HTMLResponse(content=_render_closed_requests_html(items))
    return RequestListResponse(total=len(items), requests=items)


@app.get("/requests/completed", response_model=RequestListResponse)
async def list_completed_requests(request: Request):
    """List only successfully completed analysis requests."""
    rows = await list_requests("completed", db_path=DB_PATH)
    base_url = str(request.base_url).rstrip("/")
    items = [_build_status(r, base_url) for r in rows]
    if _wants_html_response(request):
        return HTMLResponse(content=_render_closed_requests_html(items))
    return RequestListResponse(total=len(items), requests=items)


@app.get("/batching/schedules", response_model=BatchScheduleListResponse)
async def list_batched_schedules(request: Request):
    """List all configured batch schedules with latest run info."""
    rows = await list_batch_schedules(db_path=DB_PATH)
    base_url = str(request.base_url).rstrip("/")
    schedules = [_build_batch_schedule_item(r, base_url) for r in rows]
    return BatchScheduleListResponse(total=len(schedules), schedules=schedules)


@app.get("/batching/history/{ticker}", response_class=JSONResponse)
async def get_batching_history(ticker: str, provider: Optional[str] = None, limit: int = 20):
    """Get recommendation/date history for a ticker (optionally filtered by provider)."""
    cleaned_ticker = ticker.strip().upper()
    if not cleaned_ticker:
        raise HTTPException(status_code=400, detail="ticker must not be empty")
    rows = await get_recommendation_history(
        ticker=cleaned_ticker,
        llm_provider=(provider or None),
        limit=limit,
        db_path=DB_PATH,
    )
    latest = rows[0] if rows else None
    return JSONResponse(
        content={
            "ticker": cleaned_ticker,
            "provider": (provider or "").strip().lower() or None,
            "latest_final_recommendation": latest.get("recommendation") if latest else None,
            "history": rows,
        }
    )


@app.post("/batching/schedules", response_model=BatchScheduleItem, status_code=201)
async def create_batched_schedule(body: BatchScheduleCreateRequest, request: Request):
    """Create a recurring batch schedule entry."""
    ticker = body.ticker.strip().upper()
    if not ticker:
        raise HTTPException(status_code=400, detail="ticker must not be empty")

    llm_provider = (body.llm_provider or "").strip().lower()
    if llm_provider not in _SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=(
                "llm_provider must be one of: "
                + ", ".join(sorted(_SUPPORTED_PROVIDERS))
            ),
        )

    frequency = (body.frequency or "").strip().lower()
    if frequency not in _SUPPORTED_BATCH_FREQUENCIES:
        raise HTTPException(status_code=400, detail="frequency must be one of: daily, weekly, monthly")

    schedule_id = await create_batch_schedule(
        ticker=ticker,
        llm_provider=llm_provider,
        frequency=frequency,
        next_run_at=_utc_now().isoformat(),
        db_path=DB_PATH,
    )
    row = {
        "id": schedule_id,
        "ticker": ticker,
        "llm_provider": llm_provider,
        "frequency": frequency,
        "next_run_at": _utc_now().isoformat(),
        "last_run_at": None,
        "latest_recommendation": None,
        "latest_submitted_at": None,
        "latest_completed_at": None,
        "latest_request_id": None,
        "latest_analysis_file": None,
    }
    base_url = str(request.base_url).rstrip("/")
    return _build_batch_schedule_item(row, base_url)


@app.delete("/batching/schedules/{schedule_id}", response_class=JSONResponse)
async def delete_batched_schedule(schedule_id: str):
    """Delete a recurring batch schedule entry."""
    deleted = await delete_batch_schedule(schedule_id=schedule_id, db_path=DB_PATH)
    if not deleted:
        raise HTTPException(status_code=404, detail="Batch schedule not found")
    return JSONResponse(content={"id": schedule_id, "deleted": True})


@app.put("/batching/schedules/{schedule_id}", response_model=BatchScheduleItem)
async def update_batched_schedule(schedule_id: str, body: BatchScheduleUpdateRequest, request: Request):
    """Update provider/frequency for future runs of one schedule."""
    schedule = await get_batch_schedule(schedule_id=schedule_id, db_path=DB_PATH)
    if not schedule:
        raise HTTPException(status_code=404, detail="Batch schedule not found")

    llm_provider = (body.llm_provider or "").strip().lower()
    if llm_provider not in _SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=(
                "llm_provider must be one of: "
                + ", ".join(sorted(_SUPPORTED_PROVIDERS))
            ),
        )

    frequency = (body.frequency or "").strip().lower()
    if frequency not in _SUPPORTED_BATCH_FREQUENCIES:
        raise HTTPException(status_code=400, detail="frequency must be one of: daily, weekly, monthly")

    # Rebase next run from now so updated cadence applies immediately to subsequent schedule triggers.
    next_run_at = _next_run_utc_iso(frequency)
    updated = await update_batch_schedule_config(
        schedule_id=schedule_id,
        llm_provider=llm_provider,
        frequency=frequency,
        next_run_at=next_run_at,
        db_path=DB_PATH,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Batch schedule not found")

    rows = await list_batch_schedules(db_path=DB_PATH)
    row = next((r for r in rows if r.get("id") == schedule_id), None)
    if not row:
        raise HTTPException(status_code=404, detail="Batch schedule not found")
    base_url = str(request.base_url).rstrip("/")
    return _build_batch_schedule_item(row, base_url)


@app.post("/batching/schedules/{schedule_id}/rerun", response_model=SubmitResponse, status_code=202)
async def rerun_batched_schedule(schedule_id: str, body: BatchScheduleRerunRequest):
    """Trigger an immediate rerun for one schedule using the selected provider."""
    schedule = await get_batch_schedule(schedule_id=schedule_id, db_path=DB_PATH)
    if not schedule:
        raise HTTPException(status_code=404, detail="Batch schedule not found")

    llm_provider = (body.llm_provider or "").strip().lower()
    if llm_provider not in _SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=(
                "llm_provider must be one of: "
                + ", ".join(sorted(_SUPPORTED_PROVIDERS))
            ),
        )

    now_iso = _utc_now().isoformat()
    analysis_date = _latest_business_date_iso()
    req_id = await create_request(
        ticker=schedule["ticker"],
        analysis_date=analysis_date,
        llm_provider=llm_provider,
        available_after=now_iso,
        db_path=DB_PATH,
    )
    await task_queue.put((req_id, schedule["ticker"], analysis_date))

    return SubmitResponse(
        request_id=req_id,
        ticker=schedule["ticker"],
        analysis_date=analysis_date,
        llm_provider=llm_provider,
        status="pending",
        submitted_at=now_iso,
    )


@app.post("/requests/{request_id}/cancel", response_model=CancelResponse)
async def cancel_open_request(request_id: str):
    """Cancel a pending/running request."""
    row = await get_request(request_id, db_path=DB_PATH)
    if not row:
        raise HTTPException(status_code=404, detail="Request not found")
    if row.get("status") not in ("pending", "running"):
        raise HTTPException(status_code=409, detail="Only pending/running requests can be canceled")

    canceled = await cancel_request(request_id, db_path=DB_PATH)
    if not canceled:
        raise HTTPException(status_code=409, detail="Request is no longer open")

    updated = await get_request(request_id, db_path=DB_PATH)
    return CancelResponse(
        request_id=request_id,
        status="canceled",
        canceled_at=updated["completed_at"] if updated and updated.get("completed_at") else datetime.datetime.now(datetime.timezone.utc).isoformat(),
    )


@app.post("/requests/cancel-all", response_model=CancelAllResponse)
async def cancel_all_open_requests_endpoint():
    """Cancel all pending/running requests."""
    count = await cancel_all_open_requests(db_path=DB_PATH)
    return CancelAllResponse(
        canceled_count=count,
        canceled_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    )


@app.get("/env/{var_name}", response_model=EnvVarValueResponse)
async def get_env_var(var_name: str):
    """Get one allowed env variable value from process or .env file."""
    name = _validate_env_name(var_name)
    process_value = os.getenv(name)
    file_value = _read_env_file_value(name)
    value = process_value if process_value is not None else file_value
    return EnvVarValueResponse(name=name, value=value, exists=value is not None)


@app.get("/env", response_class=JSONResponse)
async def list_env_vars():
    keys = _read_env_keys()
    items = []
    for name in keys:
        process_value = os.getenv(name)
        file_value = _read_env_file_value(name)
        value = process_value if process_value is not None else file_value
        items.append({"name": name, "value": value, "exists": value is not None})
    return JSONResponse(content={"total": len(items), "items": items})


@app.put("/env/{var_name}", response_model=EnvVarValueResponse)
async def set_env_var(var_name: str, body: EnvVarUpdateRequest):
    """Update one allowed env variable in runtime env and in .env."""
    name = _validate_env_name(var_name)
    os.environ[name] = body.value
    _upsert_env_file_value(name, body.value)
    return EnvVarValueResponse(name=name, value=body.value, exists=True)


@app.post("/vault/refresh", response_model=VaultRefreshResponse)
async def force_refresh_vault_keys():
    """Force immediate reload of configured API keys from HashiCorp Vault."""
    try:
        summary = _refresh_vault_keys_and_persist()
    except VaultError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return VaultRefreshResponse(**summary)


@app.get("/recommendations/latest/{ticker}", response_model=LatestRecommendationResponse)
async def latest_recommendation_for_ticker(ticker: str, provider: Optional[str] = None):
    """Return latest completed recommendation for a stock ticker, if available."""
    cleaned_ticker = ticker.strip().upper()
    if not cleaned_ticker:
        raise HTTPException(status_code=400, detail="ticker must not be empty")

    normalized_provider = (provider or "").strip().lower() or None
    rows = await get_recommendation_history(
        ticker=cleaned_ticker,
        llm_provider=normalized_provider,
        limit=1,
        db_path=DB_PATH,
    )
    latest = rows[0] if rows else None
    return LatestRecommendationResponse(
        ticker=cleaned_ticker,
        provider=normalized_provider,
        available=latest is not None,
        latest=latest,
    )


@app.get("/metrics/llm-calls/today", response_class=JSONResponse)
async def get_today_llm_calls_by_provider():
    """Return today's LLM calls grouped by provider (UTC day), including in-flight requests."""
    now = _utc_now()
    start = datetime.datetime.combine(now.date(), datetime.time.min, tzinfo=datetime.timezone.utc)
    end = start + datetime.timedelta(days=1)
    # Completed requests from DB
    db_items = await get_llm_calls_by_provider_between(
        start_iso=start.isoformat(),
        end_iso=end.isoformat(),
        db_path=DB_PATH,
    )
    db_usage_items = await get_llm_usage_by_provider_between(
        start_iso=start.isoformat(),
        end_iso=end.isoformat(),
        db_path=DB_PATH,
    )
    # Merge in-flight (running) counts from the live counter
    merged: dict[str, int] = {row["llm_provider"]: int(row.get("llm_calls") or 0) for row in db_items}
    provider_usage: dict[str, dict] = {
        row["llm_provider"]: {
            "llm_provider": row["llm_provider"],
            "llm_calls": int(row.get("llm_calls") or 0),
            "tokens_in": int(row.get("tokens_in") or 0),
            "tokens_out": int(row.get("tokens_out") or 0),
            "total_tokens": int(row.get("total_tokens") or 0),
        }
        for row in db_usage_items
    }
    for provider, live_count in get_live_provider_calls().items():
        merged[provider] = merged.get(provider, 0) + live_count
        if provider not in provider_usage:
            provider_usage[provider] = {
                "llm_provider": provider,
                "llm_calls": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "total_tokens": 0,
            }
        provider_usage[provider]["llm_calls"] = int(provider_usage[provider].get("llm_calls") or 0) + int(live_count)
    role_items = await get_llm_role_stats_between(
        start_iso=start.isoformat(),
        end_iso=end.isoformat(),
        db_path=DB_PATH,
    )
    items = [provider_usage[p] for p, _ in sorted(merged.items(), key=lambda x: -x[1])]
    total = sum(x["llm_calls"] for x in items)
    return JSONResponse(
        content={
            "date_utc": start.date().isoformat(),
            "total_llm_calls": total,
            "providers": items,
            "roles": role_items,
        }
    )


# ---------------------------------------------------------------------------
# GET /analysis/{filename}
# ---------------------------------------------------------------------------
@app.get("/analysis/{filename}")
async def get_analysis_file(filename: str):
    """Download or view the full detailed analysis text for a completed request."""
    # Path traversal guard
    safe = Path(filename).name
    if safe != filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    filepath = Path(ANALYSIS_DIR) / safe
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Analysis file not found")
    return FileResponse(
        path=str(filepath),
        media_type="text/plain",
        filename=safe,
    )


@app.get("/logs/{request_id}", response_class=PlainTextResponse)
async def get_live_logs(request_id: str):
        """Return debug logs for a request under process."""
        row = await get_request(request_id, db_path=DB_PATH)
        if not row:
                raise HTTPException(status_code=404, detail="Request not found")
        log_path = Path(ANALYSIS_DIR) / f"{request_id}.live.log"
        if not log_path.exists():
                return ""
        return log_path.read_text(encoding="utf-8", errors="replace")


@app.get("/ui", response_class=HTMLResponse)
async def ui():
        """Minimal operations UI to monitor and cancel active requests."""
        return """
<!doctype html>
<html>
<head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>TradingAgents Operations UI</title>
    <style>
        :root { --bg:#f5f6f8; --card:#ffffff; --fg:#111827; --muted:#6b7280; --accent:#0f766e; --danger:#b91c1c; }
        body { margin:0; font-family: Segoe UI, sans-serif; background:linear-gradient(120deg,#eef2ff,#ecfeff); color:var(--fg); }
        .wrap { max-width: 1100px; margin: 24px auto; padding: 0 16px; }
        .grid { display:grid; grid-template-columns: 360px 1fr; gap:16px; }
        .card { background:var(--card); border-radius:12px; padding:14px; box-shadow:0 8px 24px rgba(0,0,0,.08); }
        h1 { margin: 0 0 12px; font-size: 22px; }
        h2 { margin: 0 0 8px; font-size: 16px; }
        .req { border:1px solid #e5e7eb; border-radius:10px; padding:10px; margin-bottom:8px; }
        .muted { color:var(--muted); font-size:12px; }
        button { border:0; border-radius:8px; padding:8px 10px; cursor:pointer; }
        .primary { background:var(--accent); color:white; }
        .danger { background:var(--danger); color:white; }
        pre { background:#0b1220; color:#d1fae5; border-radius:10px; padding:12px; height:520px; overflow:auto; white-space:pre-wrap; }
    </style>
</head>
<body>
    <div class=\"wrap\">
        <h1>TradingAgents Operations</h1>
        <div style=\"margin-bottom:12px;display:flex;gap:8px;flex-wrap:wrap;justify-content:center\">
            <a href=\"/ui\" style=\"background:#374151;color:#fff;padding:8px 10px;border-radius:8px;text-decoration:none;font-weight:600\">Operations</a>
            <a href=\"/batching\" style=\"background:#0f766e;color:#fff;padding:8px 10px;border-radius:8px;text-decoration:none;font-weight:600\">Batching</a>
            <a href=\"/completed\" style=\"background:#111827;color:#fff;padding:8px 10px;border-radius:8px;text-decoration:none;font-weight:600\">Completed</a>
            <a href=\"/requests/closed?format=html\" style=\"background:#7c3aed;color:#fff;padding:8px 10px;border-radius:8px;text-decoration:none;font-weight:600\">Closed</a>
            <a href=\"/settings\" style=\"background:#1d4ed8;color:#fff;padding:8px 10px;border-radius:8px;text-decoration:none;font-weight:600\">Settings</a>
        </div>
        <div class=\"grid\">
            <section class=\"card\">
                <h2>Create Request</h2>
                <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:12px">
                    <input id="new-ticker" type="text" placeholder="Ticker (e.g. NVDA)" style="padding:8px;border:1px solid #d1d5db;border-radius:8px;min-width:150px" />
                    <input id="new-date" type="date" style="padding:8px;border:1px solid #d1d5db;border-radius:8px" />
                    <select id="new-provider" style="padding:8px;border:1px solid #d1d5db;border-radius:8px">
                        <option value="ollama" selected>Ollama (default)</option>
                        <option value="google">Google Gemini</option>
                        <option value="openrouter">OpenRouter (free models)</option>
                    </select>
                    <button id="create-request" class="primary">Create</button>
                </div>
                <div id="create-msg" class="muted" style="margin-bottom:12px"></div>
                <h2>Open Requests</h2>
                <div style=\"margin-bottom:10px\">
                    <button id=\"cancel-all\" class=\"danger\">Cancel All Open Requests</button>
                </div>
                <div id=\"open-list\"></div>
            </section>
            <section class=\"card\">
                <h2>Debug Logs (Selected Request)</h2>
                <div class=\"muted\" id=\"selected\">No request selected</div>
                <pre id=\"logs\"></pre>
            </section>
        </div>
    </div>
    <script>
        let selectedId = null;

        async function cancelReq(id) {
            await fetch(`/requests/${id}/cancel`, { method: 'POST' });
            await refreshOpen();
        }

        async function refreshOpen() {
            const res = await fetch('/requests/open');
            const data = await res.json();
            const root = document.getElementById('open-list');
            root.innerHTML = '';
            for (const r of data.requests) {
                const div = document.createElement('div');
                div.className = 'req';
                div.innerHTML = `
                    <div><strong>${r.ticker}</strong> (${r.analysis_date})</div>
                    <div class=\"muted\">${r.request_id}</div>
                    <div class=\"muted\">status: ${r.status}</div>
                    <div class=\"muted\">provider: ${r.llm_provider || '-'}</div>
                    <div style=\"margin-top:8px;display:flex;gap:8px\">
                        <button class=\"primary\" data-sel=\"${r.request_id}\">View Logs</button>
                        <button class=\"danger\" data-cancel=\"${r.request_id}\">Cancel</button>
                    </div>
                `;
                root.appendChild(div);
            }

            root.querySelectorAll('[data-sel]').forEach(b => {
                b.addEventListener('click', () => {
                    selectedId = b.getAttribute('data-sel');
                    document.getElementById('selected').textContent = selectedId;
                });
            });
            root.querySelectorAll('[data-cancel]').forEach(b => {
                b.addEventListener('click', () => cancelReq(b.getAttribute('data-cancel')));
            });
        }

        async function refreshLogs() {
            if (!selectedId) return;
            const res = await fetch(`/logs/${selectedId}`);
            const text = await res.text();
            document.getElementById('logs').textContent = text || '[waiting for log output]';
        }

        async function createRequest() {
            const ticker = (document.getElementById('new-ticker').value || '').trim().toUpperCase();
            const date = (document.getElementById('new-date').value || '').trim();
            const llm_provider = (document.getElementById('new-provider').value || 'ollama').trim();
            const msg = document.getElementById('create-msg');

            if (!ticker) {
                msg.textContent = 'Ticker is required.';
                return;
            }

            const payload = { ticker };
            if (date) payload.date = date;
            payload.llm_provider = llm_provider;

            const res = await fetch('/analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });

            const data = await res.json();
            if (!res.ok) {
                msg.textContent = `Failed: ${data.detail || 'request error'}`;
                return;
            }

            msg.textContent = `Created request: ${data.request_id} (${data.llm_provider})`;
            document.getElementById('new-ticker').value = '';
            await refreshOpen();
        }

        async function cancelAll() {
            await fetch('/requests/cancel-all', { method: 'POST' });
            selectedId = null;
            document.getElementById('selected').textContent = 'No request selected';
            document.getElementById('logs').textContent = '';
            await refreshOpen();
        }

        document.getElementById('cancel-all').addEventListener('click', cancelAll);
        document.getElementById('create-request').addEventListener('click', createRequest);

        refreshOpen();
        setInterval(refreshOpen, 3000);
        setInterval(refreshLogs, 1500);
    </script>
</body>
</html>
        """


@app.get("/batching", response_class=HTMLResponse)
async def batching_page():
    """Batching screen for recurring ticker/provider runs."""
    return """
<!doctype html>
<html>
<head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>TradingAgents Batching</title>
    <style>
        :root { --bg:#f5f8ff; --paper:#ffffff; --ink:#101827; --muted:#5b6470; --line:#d4def2; --brand:#1d4ed8; --brand-2:#2563eb; }
        * { box-sizing:border-box; }
        body { margin:0; font-family: Segoe UI, Tahoma, sans-serif; color:var(--ink); background: radial-gradient(circle at 0% 0%, #dbeafe, #f5f8ff 45%, #eafaf2 100%); }
        .wrap { max-width:1180px; margin:24px auto; padding:0 14px; }
        .head { display:flex; justify-content:space-between; align-items:flex-end; gap:12px; margin-bottom:12px; flex-wrap:wrap; }
        h1 { margin:0; font-size:30px; }
        .muted { color:var(--muted); font-size:13px; }
        .card { background:var(--paper); border:1px solid var(--line); border-radius:14px; box-shadow:0 12px 30px rgba(16,24,39,0.08); padding:14px; }
        .toolbar { display:grid; grid-template-columns: repeat(5, minmax(120px, 1fr)); gap:10px; align-items:end; }
        label { display:block; font-size:12px; color:var(--muted); margin-bottom:4px; }
        input, select { width:100%; border:1px solid #c8d4ef; border-radius:10px; padding:10px; font-size:14px; }
        button { border:0; border-radius:10px; padding:10px 14px; cursor:pointer; font-weight:700; }
        .primary { background:linear-gradient(135deg, var(--brand), var(--brand-2)); color:#fff; }
        .table-wrap { margin-top:14px; overflow:auto; border:1px solid var(--line); border-radius:12px; }
        table { width:100%; border-collapse:collapse; min-width:940px; }
        th, td { padding:10px 12px; text-align:left; border-bottom:1px solid #e7eefc; font-size:14px; vertical-align:top; }
        th { background:#eff6ff; color:#1e3a8a; font-weight:700; }
        tr:hover td { background:#f8fbff; }
        .pill { display:inline-block; padding:4px 8px; border-radius:999px; background:#e0ebff; color:#1e3a8a; font-size:12px; font-weight:700; text-transform:capitalize; }
        .link { color:#1d4ed8; text-decoration:none; font-weight:600; }
        .link:hover { text-decoration:underline; }
        .rec { max-width:330px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .rec-link { color:#1d4ed8; text-decoration:underline; font-weight:600; cursor:pointer; display:inline-block; max-width:330px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .modal { display:none; position:fixed; inset:0; background:rgba(15,23,42,0.55); z-index:1000; }
        .modal-content { background:#fff; max-width:900px; margin:32px auto; border-radius:12px; padding:14px; max-height:86vh; overflow:auto; box-shadow:0 18px 46px rgba(15,23,42,0.35); }
        .modal-head { display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; }
        .modal-close { border:0; background:#ef4444; color:#fff; border-radius:8px; padding:6px 10px; cursor:pointer; font-weight:700; }
        .history { width:100%; border-collapse:collapse; margin-top:8px; }
        .history th, .history td { border-bottom:1px solid #e5e7eb; text-align:left; padding:8px 10px; font-size:13px; }
        .history th { background:#f8fafc; }
        .final-box { background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px; padding:10px; white-space:pre-wrap; word-break:break-word; }
        .actions { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
        .mini-btn { border:0; border-radius:8px; padding:6px 10px; cursor:pointer; font-weight:700; font-size:12px; }
        .danger { background:#dc2626; color:#fff; }
        .secondary { background:#1d4ed8; color:#fff; }
        .warning { background:#0f766e; color:#fff; }
        .row-provider { min-width:130px; padding:6px 8px; font-size:12px; border-radius:8px; }
        .row-frequency { min-width:120px; padding:6px 8px; font-size:12px; border-radius:8px; display:none; }
        @media (max-width: 960px) {
            .toolbar { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <main class=\"wrap\">
        <div class=\"head\">
            <div>
                <h1>Batching</h1>
                <p class=\"muted\">Create and monitor recurring ticker runs by provider and frequency.</p>
            </div>
            <div style="display:flex;gap:8px;flex-wrap:wrap;justify-content:center;flex:1 1 100%">
                <a href="/ui" style="background:#374151;color:#fff;padding:8px 10px;border-radius:8px;text-decoration:none;font-weight:600">Operations</a>
                <a href="/batching" style="background:#0f766e;color:#fff;padding:8px 10px;border-radius:8px;text-decoration:none;font-weight:600">Batching</a>
                <a href="/completed" style="background:#111827;color:#fff;padding:8px 10px;border-radius:8px;text-decoration:none;font-weight:600">Completed</a>
                <a href="/requests/closed?format=html" style="background:#7c3aed;color:#fff;padding:8px 10px;border-radius:8px;text-decoration:none;font-weight:600">Closed</a>
                <a href="/settings" style="background:#1d4ed8;color:#fff;padding:8px 10px;border-radius:8px;text-decoration:none;font-weight:600">Settings</a>
            </div>
        </div>

        <section class=\"card\">
            <div class=\"toolbar\">
                <div>
                    <label for=\"ticker\">Ticker</label>
                    <input id=\"ticker\" placeholder=\"e.g. NVDA\" />
                </div>
                <div>
                    <label for=\"provider\">Provider</label>
                    <select id=\"provider\">
                        <option value=\"ollama\">Ollama</option>
                        <option value=\"google\">Google</option>
                        <option value="openrouter">OpenRouter</option>
                    </select>
                </div>
                <div>
                    <label for=\"frequency\">Frequency</label>
                    <select id=\"frequency\">
                        <option value=\"daily\">Daily</option>
                        <option value=\"weekly\">Weekly</option>
                        <option value=\"monthly\">Monthly</option>
                    </select>
                </div>
                <div>
                    <button id=\"add\" class=\"primary\">Add Schedule</button>
                </div>
                <div class=\"muted\" id=\"message\"></div>
            </div>

            <div class=\"table-wrap\">
                <table>
                    <thead>
                        <tr>
                            <th>Ticker</th>
                            <th>Provider</th>
                            <th>Frequency</th>
                            <th>Latest Recommendation</th>
                            <th>Last Run Date & Time</th>
                            <th>Latest Run Logs</th>
                            <th>Latest Analysis</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody id=\"rows\"></tbody>
                </table>
            </div>
        </section>
    </main>

    <div id=\"historyModal\" class=\"modal\">
        <div class=\"modal-content\">
            <div class=\"modal-head\">
                <h2 id=\"historyTitle\" style=\"margin:0\">Recommendation History</h2>
                <button id=\"historyClose\" class=\"modal-close\">Close</button>
            </div>
            <div>
                <div class=\"muted\" style=\"margin-bottom:6px\">Latest Final Recommendation</div>
                <div id=\"historyLatest\" class=\"final-box\">—</div>
            </div>
            <div style=\"margin-top:12px\">
                <div class=\"muted\" style=\"margin-bottom:6px\">Date History</div>
                <table class=\"history\">
                    <thead>
                        <tr>
                            <th>Completed At</th>
                            <th>Analysis Date</th>
                            <th>Provider</th>
                            <th>Recommendation (Preview)</th>
                        </tr>
                    </thead>
                    <tbody id=\"historyRows\"></tbody>
                </table>
            </div>
        </div>
    </div>

    <script>
        let editingScheduleId = null;

        function safe(value) {
            return (value || '').toString().replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#039;');
        }

        function formatTime(value) {
            if (!value) return '—';
            const d = new Date(value);
            if (Number.isNaN(d.getTime())) return safe(value);
            return d.toLocaleString();
        }

        async function loadSchedules() {
            const res = await fetch('/batching/schedules');
            const data = await res.json();
            const root = document.getElementById('rows');
            root.innerHTML = '';
            for (const item of data.schedules || []) {
                const rec = item.latest_recommendation || '—';
                const logs = item.latest_logs_url ? `<a class="link" href="${safe(item.latest_logs_url)}" target="_blank">Logs</a>` : '—';
                const analysis = item.latest_analysis_url ? `<a class="link" href="${safe(item.latest_analysis_url)}" target="_blank">Analysis</a>` : '—';
                const providerSelect = `
                    <select class="row-provider" data-provider-id="${safe(item.id)}">
                        <option value="ollama" ${item.llm_provider === 'ollama' ? 'selected' : ''}>Ollama</option>
                        <option value="google" ${item.llm_provider === 'google' ? 'selected' : ''}>Google</option>
                        <option value="openrouter" ${item.llm_provider === 'openrouter' ? 'selected' : ''}>OpenRouter</option>
                    </select>
                `;
                const frequencySelect = `
                    <select class="row-frequency" data-frequency-id="${safe(item.id)}">
                        <option value="daily" ${item.frequency === 'daily' ? 'selected' : ''}>Daily</option>
                        <option value="weekly" ${item.frequency === 'weekly' ? 'selected' : ''}>Weekly</option>
                        <option value="monthly" ${item.frequency === 'monthly' ? 'selected' : ''}>Monthly</option>
                    </select>
                `;
                const recLink = rec === '—'
                    ? '—'
                    : `<a href="#" class="rec-link" data-rec-ticker="${safe(item.ticker)}" data-rec-provider="${safe(item.llm_provider)}" title="${safe(rec)}">${safe(rec)}</a>`;
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${safe(item.ticker)}</td>
                    <td>${safe(item.llm_provider)}</td>
                    <td><span class="pill">${safe(item.frequency)}</span></td>
                    <td><div class="rec" title="${safe(rec)}">${recLink}</div></td>
                    <td>${formatTime(item.last_run_at)}</td>
                    <td>${logs}</td>
                    <td>${analysis}</td>
                    <td>
                        <div class="actions">
                            ${providerSelect}
                            ${frequencySelect}
                            <button class="mini-btn warning" data-edit-id="${safe(item.id)}" data-editing="false">Edit</button>
                            <button class="mini-btn secondary" data-rerun-id="${safe(item.id)}">Rerun</button>
                            <button class="mini-btn danger" data-delete-id="${safe(item.id)}">Delete</button>
                        </div>
                    </td>
                `;
                root.appendChild(tr);
            }

            root.querySelectorAll('[data-rec-ticker]').forEach((el) => {
                el.addEventListener('click', async (ev) => {
                    ev.preventDefault();
                    const ticker = el.getAttribute('data-rec-ticker') || '';
                    const provider = el.getAttribute('data-rec-provider') || '';
                    await showRecommendationHistory(ticker, provider);
                });
            });

            root.querySelectorAll('[data-delete-id]').forEach((el) => {
                el.addEventListener('click', async () => {
                    const id = el.getAttribute('data-delete-id');
                    await deleteSchedule(id || '');
                });
            });

            root.querySelectorAll('[data-rerun-id]').forEach((el) => {
                el.addEventListener('click', async () => {
                    const id = el.getAttribute('data-rerun-id');
                    await rerunSchedule(id || '');
                });
            });

            root.querySelectorAll('[data-edit-id]').forEach((el) => {
                el.addEventListener('click', async () => {
                    const id = el.getAttribute('data-edit-id');
                    await toggleEditSave(id || '', el);
                });
            });
        }

        async function toggleEditSave(scheduleId, buttonEl) {
            const message = document.getElementById('message');
            if (!scheduleId || !buttonEl) return;

            const providerEl = document.querySelector(`[data-provider-id="${CSS.escape(scheduleId)}"]`);
            const frequencyEl = document.querySelector(`[data-frequency-id="${CSS.escape(scheduleId)}"]`);
            if (!providerEl || !frequencyEl) return;

            const editing = buttonEl.getAttribute('data-editing') === 'true';
            if (!editing) {
                if (editingScheduleId && editingScheduleId !== scheduleId) {
                    message.textContent = 'Save or reload the currently edited row before editing another.';
                    return;
                }
                editingScheduleId = scheduleId;
                frequencyEl.style.display = 'inline-block';
                buttonEl.setAttribute('data-editing', 'true');
                buttonEl.textContent = 'Save';
                message.textContent = 'Edit mode enabled. Update provider/frequency and click Save.';
                return;
            }

            const llm_provider = providerEl.value || 'ollama';
            const frequency = frequencyEl.value || 'daily';
            const res = await fetch(`/batching/schedules/${encodeURIComponent(scheduleId)}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ llm_provider, frequency }),
            });
            const data = await res.json();
            if (!res.ok) {
                message.textContent = `Save failed: ${data.detail || 'request error'}`;
                return;
            }

            editingScheduleId = null;
            message.textContent = `Schedule updated: ${data.ticker} (${data.llm_provider}, ${data.frequency})`;
            await loadSchedules();
        }

        async function deleteSchedule(scheduleId) {
            const message = document.getElementById('message');
            if (!scheduleId) return;
            const ok = window.confirm('Delete this stock from batch schedules?');
            if (!ok) return;

            const res = await fetch(`/batching/schedules/${encodeURIComponent(scheduleId)}`, {
                method: 'DELETE',
            });
            const data = await res.json();
            if (!res.ok) {
                message.textContent = `Delete failed: ${data.detail || 'request error'}`;
                return;
            }
            message.textContent = 'Schedule deleted successfully.';
            await loadSchedules();
        }

        async function rerunSchedule(scheduleId) {
            const message = document.getElementById('message');
            if (!scheduleId) return;
            const providerEl = document.querySelector(`[data-provider-id="${CSS.escape(scheduleId)}"]`);
            const llm_provider = (providerEl && providerEl.value) ? providerEl.value : 'ollama';

            const res = await fetch(`/batching/schedules/${encodeURIComponent(scheduleId)}/rerun`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ llm_provider }),
            });
            const data = await res.json();
            if (!res.ok) {
                message.textContent = `Rerun failed: ${data.detail || 'request error'}`;
                return;
            }
            message.textContent = `Rerun queued for ${data.ticker} (${data.llm_provider})`;
        }

        async function showRecommendationHistory(ticker, provider) {
            const modal = document.getElementById('historyModal');
            const title = document.getElementById('historyTitle');
            const latest = document.getElementById('historyLatest');
            const rows = document.getElementById('historyRows');
            title.textContent = `Recommendation History: ${ticker} (${provider || 'all'})`;
            latest.textContent = 'Loading...';
            rows.innerHTML = '<tr><td colspan="4">Loading...</td></tr>';
            modal.style.display = 'block';

            const qs = provider ? `?provider=${encodeURIComponent(provider)}&limit=50` : '?limit=50';
            const res = await fetch(`/batching/history/${encodeURIComponent(ticker)}${qs}`);
            const data = await res.json();
            if (!res.ok) {
                latest.textContent = 'Failed to load recommendation history.';
                rows.innerHTML = `<tr><td colspan="4">${safe(data.detail || 'request error')}</td></tr>`;
                return;
            }

            latest.textContent = data.latest_final_recommendation || '—';
            const history = data.history || [];
            if (!history.length) {
                rows.innerHTML = '<tr><td colspan="4">No history found.</td></tr>';
                return;
            }

            rows.innerHTML = history.map((h) => {
                const rec = (h.recommendation || '—');
                const preview = rec.length > 140 ? `${rec.slice(0, 140)}...` : rec;
                return `<tr>
                    <td>${formatTime(h.completed_at)}</td>
                    <td>${safe(h.analysis_date || '—')}</td>
                    <td>${safe(h.llm_provider || '—')}</td>
                    <td title="${safe(rec)}">${safe(preview)}</td>
                </tr>`;
            }).join('');
        }

        async function addSchedule() {
            const ticker = (document.getElementById('ticker').value || '').trim().toUpperCase();
            const llm_provider = (document.getElementById('provider').value || 'ollama').trim();
            const frequency = (document.getElementById('frequency').value || 'daily').trim();
            const message = document.getElementById('message');

            if (!ticker) {
                message.textContent = 'Ticker is required.';
                return;
            }

            const res = await fetch('/batching/schedules', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ticker, llm_provider, frequency }),
            });
            const data = await res.json();

            if (!res.ok) {
                message.textContent = `Failed: ${data.detail || 'request error'}`;
                return;
            }

            document.getElementById('ticker').value = '';
            message.textContent = `Added ${data.ticker} (${data.llm_provider}, ${data.frequency})`;
            await loadSchedules();
        }

        document.getElementById('add').addEventListener('click', addSchedule);
        document.getElementById('historyClose').addEventListener('click', () => {
            document.getElementById('historyModal').style.display = 'none';
        });
        document.getElementById('historyModal').addEventListener('click', (ev) => {
            if (ev.target.id === 'historyModal') {
                document.getElementById('historyModal').style.display = 'none';
            }
        });
        loadSchedules();
        setInterval(() => {
            if (editingScheduleId) return;
            loadSchedules();
        }, 10000);
    </script>
</body>
</html>
    """


@app.get("/settings", response_class=HTMLResponse)
async def settings_page():
    """Settings screen for runtime environment values and usage metrics."""
    mcp_button = (
        '<a class="ghost-btn mcp" href="/mcp-server" target="_blank" rel="noopener noreferrer">MCP Server</a>'
        if _HAS_MCP_SERVER
        else ""
    )
    return """
<!doctype html>
<html>
<head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>TradingAgents Settings</title>
    <style>
        :root { --bg:#f8fafc; --panel:#ffffff; --ink:#0f172a; --muted:#475569; --line:#dbe2ee; --brand:#0ea5e9; }
        body { margin:0; font-family: Segoe UI, Tahoma, sans-serif; color:var(--ink); background: radial-gradient(circle at 0% 0%, #e0f2fe, #f8fafc 45%, #f1f5f9 100%); }
        .wrap { max-width: 860px; margin: 24px auto; padding: 0 14px; }
        .card { background:var(--panel); border:1px solid var(--line); border-radius:14px; padding:16px; box-shadow:0 10px 28px rgba(15,23,42,0.08); }
        h1 { margin:0 0 8px; }
        .muted { color:var(--muted); font-size:13px; }
        label { display:block; font-size:12px; color:var(--muted); margin:10px 0 4px; }
        input { width:100%; border:1px solid #c9d6e8; border-radius:10px; padding:10px; font-size:14px; }
        .row { display:flex; gap:8px; align-items:center; margin-top:10px; flex-wrap:wrap; }
        button { border:0; border-radius:10px; padding:10px 14px; cursor:pointer; font-weight:700; background:linear-gradient(135deg,#0284c7,#0ea5e9); color:#fff; }
        .ghost-btn { display:inline-block; text-decoration:none; border-radius:10px; padding:10px 14px; font-weight:700; background:#1d4ed8; color:#fff; }
        .ghost-btn.mcp { background:#0f766e; }
        code { background:#e2e8f0; border-radius:6px; padding:2px 6px; }
        table { width:100%; border-collapse: collapse; margin-top:10px; }
        th, td { text-align:left; padding:8px 10px; border-bottom:1px solid #e2e8f0; font-size:13px; }
        th { color:#334155; background:#f1f5f9; }
    </style>
</head>
<body>
    <main class=\"wrap\">
        <div class=\"card\">
            <div style="margin-bottom:12px;display:flex;gap:8px;flex-wrap:wrap;justify-content:center">
                <a href="/ui" style="background:#374151;color:#fff;padding:8px 10px;border-radius:8px;text-decoration:none;font-weight:600">Operations</a>
                <a href="/batching" style="background:#0f766e;color:#fff;padding:8px 10px;border-radius:8px;text-decoration:none;font-weight:600">Batching</a>
                <a href="/completed" style="background:#111827;color:#fff;padding:8px 10px;border-radius:8px;text-decoration:none;font-weight:600">Completed</a>
                <a href="/requests/closed?format=html" style="background:#7c3aed;color:#fff;padding:8px 10px;border-radius:8px;text-decoration:none;font-weight:600">Closed</a>
                <a href="/settings" style="background:#1d4ed8;color:#fff;padding:8px 10px;border-radius:8px;text-decoration:none;font-weight:600">Settings</a>
            </div>
            <h1>Settings</h1>
            <p class="muted">View and update any key from your <code>.env</code>. Type a key name to add or update it.</p>
            <div class="row" style="margin:8px 0 14px">
                <a class="ghost-btn" href="/docs" target="_blank" rel="noopener noreferrer">Swagger Definition</a>
                <a class="ghost-btn" href="/api-definition" target="_blank" rel="noopener noreferrer">API Definition</a>
                __MCP_BUTTON__
            </div>
            <label for="envName">.env key name</label>
            <input id="envName" type="text" placeholder="e.g. GOOGLE_API_KEY" />
            <label for="envValue">.env key value</label>
            <input id="envValue" type="password" placeholder="Enter value" />
            <div class=\"row\">
                <button id=\"save\">Save Key</button>
                <button id=\"reload\" type=\"button\">Force Reload</button>
                <button id="vaultRefresh" type="button">Refresh From Vault</button>
                <button id="toggleValue" type="button">Show/Hide Value</button>
                <span id=\"msg\" class=\"muted\"></span>
            </div>
            <div style="margin-top:12px">
                <div class="muted">Known .env keys</div>
                <table>
                    <thead>
                        <tr>
                            <th>Key</th>
                            <th>Current Value</th>
                        </tr>
                    </thead>
                    <tbody id="envBody"></tbody>
                </table>
            </div>
            <div style=\"margin-top:16px\">
                <div class=\"muted\" id=\"callsDate\">Today's LLM calls (UTC)</div>
                <table>
                    <thead>
                        <tr>
                            <th>Provider</th>
                            <th>LLM Calls Today</th>
                            <th>Input Tokens</th>
                            <th>Output Tokens</th>
                            <th>Total Tokens</th>
                        </tr>
                    </thead>
                    <tbody id=\"callsBody\"></tbody>
                </table>
                <div class=\"muted\" id=\"callsTotal\" style=\"margin-top:8px\"></div>
            </div>
            <div style=\"margin-top:16px\">
                <div class=\"muted\" id=\"rolesDate\">Today's LLM role split (UTC)</div>
                <table>
                    <thead>
                        <tr>
                            <th>Role</th>
                            <th>LLM Calls</th>
                            <th>Input Tokens</th>
                            <th>Output Tokens</th>
                            <th>Total Tokens</th>
                            <th>Avg Duration (s)</th>
                        </tr>
                    </thead>
                    <tbody id=\"rolesBody\"></tbody>
                </table>
            </div>
        </div>
    </main>
    <script>
        function esc(v) {
            return (v || '').toString().replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#039;');
        }

        function humanizeRole(role) {
            const text = (role || 'unknown').toString().trim();
            if (!text) return 'Unknown';
            return text
                .replaceAll('_', ' ')
                .split(' ')
                .filter(Boolean)
                .map(p => p.charAt(0).toUpperCase() + p.slice(1))
                .join(' ');
        }

        function pickEnv(name, value) {
            document.getElementById('envName').value = (name || '').toString();
            document.getElementById('envValue').value = (value || '').toString();
        }

        async function loadEnvList() {
            const root = document.getElementById('envBody');
            const res = await fetch('/env');
            const data = await res.json();
            if (!res.ok) {
                root.innerHTML = '<tr><td colspan="2">Failed to load .env keys</td></tr>';
                return;
            }
            const items = data.items || [];
            if (!items.length) {
                root.innerHTML = '<tr><td colspan="2">No keys found in .env</td></tr>';
                return;
            }

            root.innerHTML = items
                .map(item => {
                    const value = (item.value || '').toString();
                    const preview = value.length > 80 ? `${value.slice(0, 80)}...` : value;
                    return `<tr>
                        <td><a href="#" data-key="${esc(item.name)}">${esc(item.name)}</a></td>
                        <td title="${esc(value)}">${esc(preview)}</td>
                    </tr>`;
                })
                .join('');

            root.querySelectorAll('[data-key]').forEach((el) => {
                el.addEventListener('click', (ev) => {
                    ev.preventDefault();
                    const key = el.getAttribute('data-key') || '';
                    const item = items.find(i => i.name === key);
                    pickEnv(key, item ? item.value : '');
                });
            });
        }

        async function loadTodayCalls() {
            const root = document.getElementById('callsBody');
            const callsDate = document.getElementById('callsDate');
            const callsTotal = document.getElementById('callsTotal');
            const rolesDate = document.getElementById('rolesDate');
            const rolesBody = document.getElementById('rolesBody');
            const res = await fetch('/metrics/llm-calls/today');
            const data = await res.json();
            if (!res.ok) {
                root.innerHTML = '<tr><td colspan="5">Failed to load metrics</td></tr>';
                rolesBody.innerHTML = '<tr><td colspan="6">Failed to load metrics</td></tr>';
                callsTotal.textContent = '';
                return;
            }
            callsDate.textContent = `Today's LLM calls by provider (UTC date: ${data.date_utc})`;
            rolesDate.textContent = `Today's LLM call split by role (UTC date: ${data.date_utc})`;
            const providers = data.providers || [];
            if (!providers.length) {
                root.innerHTML = '<tr><td colspan="5">No completed calls today</td></tr>';
            } else {
                root.innerHTML = providers
                    .map(p => `<tr>
                        <td>${esc(p.llm_provider)}</td>
                        <td>${Number(p.llm_calls || 0).toLocaleString()}</td>
                        <td>${Number(p.tokens_in || 0).toLocaleString()}</td>
                        <td>${Number(p.tokens_out || 0).toLocaleString()}</td>
                        <td>${Number(p.total_tokens || 0).toLocaleString()}</td>
                    </tr>`)
                    .join('');
            }

            const roles = data.roles || [];
            if (!roles.length) {
                rolesBody.innerHTML = '<tr><td colspan="6">No role-level calls captured today</td></tr>';
            } else {
                rolesBody.innerHTML = roles
                    .map(r => {
                        const avg = Number(r.avg_duration_seconds || 0);
                        return `<tr>
                            <td>${esc(humanizeRole(r.role))}</td>
                            <td>${Number(r.llm_calls || 0).toLocaleString()}</td>
                            <td>${Number(r.tokens_in || 0).toLocaleString()}</td>
                            <td>${Number(r.tokens_out || 0).toLocaleString()}</td>
                            <td>${Number(r.total_tokens || 0).toLocaleString()}</td>
                            <td>${avg.toFixed(2)}</td>
                        </tr>`;
                    })
                    .join('');
            }
            callsTotal.textContent = `Total today: ${Number(data.total_llm_calls || 0).toLocaleString()} calls`;
        }

        async function reloadAll() {
            const msg = document.getElementById('msg');
            msg.textContent = 'Reloading...';
            await Promise.all([loadEnvList(), loadTodayCalls()]);
            msg.textContent = 'Reloaded values.';
        }

        async function save() {
            const name = (document.getElementById('envName').value || '').trim().toUpperCase();
            const value = document.getElementById('envValue').value || '';
            const msg = document.getElementById('msg');
            if (!name) {
                msg.textContent = 'Key name is required.';
                return;
            }
            const res = await fetch(`/env/${encodeURIComponent(name)}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ value }),
            });
            const data = await res.json();
            if (!res.ok) {
                msg.textContent = `Failed: ${data.detail || 'request error'}`;
                return;
            }
            msg.textContent = `Saved ${name}.`;
            await Promise.all([loadEnvList(), loadTodayCalls()]);
        }

        async function refreshFromVault() {
            const msg = document.getElementById('msg');
            msg.textContent = 'Refreshing from Vault...';
            const res = await fetch('/vault/refresh', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({}),
            });
            const data = await res.json();
            if (!res.ok) {
                msg.textContent = `Vault refresh failed: ${data.detail || 'request error'}`;
                return;
            }
            msg.textContent = `Vault refresh complete. Updated ${Number(data.updated || 0)} key(s).`;
            await Promise.all([loadEnvList(), loadTodayCalls()]);
        }

        function toggleValueVisibility() {
            const input = document.getElementById('envValue');
            input.type = input.type === 'password' ? 'text' : 'password';
        }

        document.getElementById('save').addEventListener('click', save);
        document.getElementById('reload').addEventListener('click', reloadAll);
        document.getElementById('vaultRefresh').addEventListener('click', refreshFromVault);
        document.getElementById('toggleValue').addEventListener('click', toggleValueVisibility);
        reloadAll();
    </script>
</body>
</html>
    """.replace("__MCP_BUTTON__", mcp_button)


# ---------------------------------------------------------------------------
# GET /completed
# ---------------------------------------------------------------------------
@app.get("/completed", response_class=HTMLResponse)
async def completed_requests_page():
    """Display completed analysis requests with agent recommendations."""
    try:
        # Try to load the HTML file from the same directory
        html_file = Path(__file__).parent / "completed_requests.html"
        if html_file.exists():
            return html_file.read_text(encoding="utf-8")
    except Exception:
        pass
    
    # Fallback if file not found
    return """
<!DOCTYPE html>
<html>
<head>
    <title>Completed Analysis Requests</title>
</head>
<body>
    <h1>Error</h1>
    <p>The completed requests page is not available. Please check the installation.</p>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# GET /healthz
# ---------------------------------------------------------------------------
@app.get("/healthz", response_class=PlainTextResponse)
async def healthz():
    """Health check."""
    return "ok"
