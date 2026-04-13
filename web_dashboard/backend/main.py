"""
TradingAgents Web Dashboard Backend
FastAPI REST API + WebSocket for real-time analysis progress
"""
import asyncio
import hmac
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from services import AnalysisService, JobService, ResultStore, build_request_context, load_migration_flags
from services.executor import LegacySubprocessAnalysisExecutor

# Path to TradingAgents repo root
REPO_ROOT = Path(__file__).parent.parent.parent
# Use the currently running Python interpreter
ANALYSIS_PYTHON = Path(sys.executable)
# Task state persistence directory
TASK_STATUS_DIR = Path(__file__).parent / "data" / "task_status"
CONFIG_PATH = Path(__file__).parent / "data" / "config.json"


# ============== Lifespan ==============

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    app.state.active_connections: dict[str, list[WebSocket]] = {}
    app.state.task_results: dict[str, dict] = {}
    app.state.analysis_tasks: dict[str, asyncio.Task] = {}
    app.state.processes: dict[str, asyncio.subprocess.Process | None] = {}
    app.state.migration_flags = load_migration_flags()

    portfolio_gateway = create_legacy_portfolio_gateway()
    app.state.result_store = ResultStore(TASK_STATUS_DIR, portfolio_gateway)
    app.state.job_service = JobService(
        task_results=app.state.task_results,
        analysis_tasks=app.state.analysis_tasks,
        processes=app.state.processes,
        persist_task=app.state.result_store.save_task_status,
        delete_task=app.state.result_store.delete_task_status,
    )
    app.state.analysis_service = AnalysisService(
        executor=LegacySubprocessAnalysisExecutor(
            analysis_python=ANALYSIS_PYTHON,
            repo_root=REPO_ROOT,
            api_key_resolver=_get_analysis_api_key,
            process_registry=app.state.job_service.register_process,
        ),
        result_store=app.state.result_store,
        job_service=app.state.job_service,
        retry_count=MAX_RETRY_COUNT,
        retry_base_delay_secs=RETRY_BASE_DELAY_SECS,
    )

    # Restore persisted task states from disk
    app.state.job_service.restore_task_results(app.state.result_store.restore_task_results())

    yield


# ============== App ==============

app = FastAPI(
    title="TradingAgents Web Dashboard API",
    version="0.1.0",
    lifespan=lifespan
)

# CORS: allow all if CORS_ORIGINS is not set (development), otherwise comma-separated list
_cors_origins = os.environ.get("CORS_ORIGINS", "*")
_cors_origins_list = ["*"] if _cors_origins == "*" else [o.strip() for o in _cors_origins.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============== Pydantic Models ==============

class AnalysisRequest(BaseModel):
    ticker: str
    date: Optional[str] = None

class ScreenRequest(BaseModel):
    mode: str = "china_strict"


# ============== Config Commands (Tauri IPC) ==============

@app.get("/api/config/check")
async def check_config():
    """Check if the app is configured (API key is set).
    The FastAPI backend receives ANTHROPIC_API_KEY as an env var when spawned by Tauri.
    """
    configured = bool(_get_analysis_api_key())
    return {"configured": configured}


@app.post("/api/config/apikey")
async def save_apikey(request: Request, body: dict = None, api_key: Optional[str] = Header(None)):
    """Persist API key for local desktop/backend use."""
    if _get_api_key():
        if not _check_api_key(api_key):
            _auth_error()
    elif not _is_local_request(request):
        raise HTTPException(status_code=403, detail="API key setup is only allowed from localhost")

    if not body or "api_key" not in body:
        raise HTTPException(status_code=400, detail="api_key is required")

    apikey = body["api_key"].strip()
    if not apikey:
        raise HTTPException(status_code=400, detail="api_key cannot be empty")

    try:
        _persist_analysis_api_key(apikey)
        return {"ok": True, "saved": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save API key: {e}")


# ============== Cache Helpers ==============

CACHE_DIR = Path(__file__).parent.parent / "cache"
CACHE_TTL_SECONDS = 300  # 5 minutes
MAX_RETRY_COUNT = 2
RETRY_BASE_DELAY_SECS = 1
MAX_CONCURRENT_YFINANCE = 5

# Pagination defaults
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 500

# Auth — set DASHBOARD_API_KEY env var to enable API key authentication
_api_key: Optional[str] = None

def _get_api_key() -> Optional[str]:
    global _api_key
    if _api_key is None:
        _api_key = os.environ.get("DASHBOARD_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    return _api_key

def _check_api_key(api_key: Optional[str]) -> bool:
    """Return True if no key is required, or if the provided key matches."""
    required = _get_api_key()
    if not required:
        return True
    if not api_key:
        return False
    return hmac.compare_digest(api_key, required)

def _auth_error():
    raise HTTPException(status_code=401, detail="Unauthorized: valid X-API-Key header required")


def _load_saved_config() -> dict:
    try:
        if CONFIG_PATH.exists():
            return json.loads(CONFIG_PATH.read_text())
    except Exception:
        pass
    return {}


def _persist_analysis_api_key(api_key_value: str):
    global _api_key
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps({"api_key": api_key_value}, ensure_ascii=False))
    os.chmod(CONFIG_PATH, 0o600)
    os.environ["ANTHROPIC_API_KEY"] = api_key_value
    _api_key = None


def _get_analysis_api_key() -> Optional[str]:
    return (
        os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("MINIMAX_API_KEY")
        or _load_saved_config().get("api_key")
    )


def _is_local_request(request: Request) -> bool:
    client = request.client
    if client is None:
        return False
    return client.host in {"127.0.0.1", "::1", "localhost", "testclient"}


def _get_cache_path(mode: str) -> Path:
    return CACHE_DIR / f"screen_{mode}.json"


def _load_from_cache(mode: str) -> Optional[dict]:
    cache_path = _get_cache_path(mode)
    if not cache_path.exists():
        return None
    try:
        age = time.time() - cache_path.stat().st_mtime
        if age > CACHE_TTL_SECONDS:
            return None
        with open(cache_path) as f:
            return json.load(f)
    except Exception:
        return None


def _save_to_cache(mode: str, data: dict):
    """Save screening result to cache"""
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path = _get_cache_path(mode)
        with open(cache_path, "w") as f:
            json.dump(data, f)
    except Exception:
        pass


# ============== SEPA Screening ==============

def _run_sepa_screening(mode: str) -> dict:
    """Run SEPA screening synchronously in thread"""
    sys.path.insert(0, str(REPO_ROOT))
    from sepa_screener import screen_all, china_stocks
    results = screen_all(mode=mode, max_workers=5)
    total = len(china_stocks)
    return {
        "mode": mode,
        "total_stocks": total,
        "passed": len(results),
        "results": results,
    }


@app.get("/api/stocks/screen")
async def screen_stocks(mode: str = Query("china_strict"), refresh: bool = Query(False), api_key: Optional[str] = Header(None)):
    """Screen stocks using SEPA criteria with caching"""
    if not _check_api_key(api_key):
        _auth_error()
    if not refresh:
        cached = _load_from_cache(mode)
        if cached:
            return {**cached, "cached": True}

    # Run in thread pool (blocks thread but not event loop)
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, lambda: _run_sepa_screening(mode))

    _save_to_cache(mode, result)
    return {**result, "cached": False}


# ============== Analysis Execution ==============

@app.post("/api/analysis/start")
async def start_analysis(
    payload: AnalysisRequest,
    http_request: Request,
    api_key: Optional[str] = Header(None),
):
    """Start a new analysis task."""
    import uuid

    if not _check_api_key(api_key):
        _auth_error()

    task_id = f"{payload.ticker}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    date = payload.date or datetime.now().strftime("%Y-%m-%d")
    request_context = build_request_context(http_request, api_key=api_key)

    try:
        return await app.state.analysis_service.start_analysis(
            task_id=task_id,
            ticker=payload.ticker,
            date=date,
            request_context=request_context,
            broadcast_progress=broadcast_progress,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/analysis/status/{task_id}")
async def get_task_status(task_id: str, api_key: Optional[str] = Header(None)):
    """Get task status"""
    if not _check_api_key(api_key):
        _auth_error()
    if task_id not in app.state.task_results:
        raise HTTPException(status_code=404, detail="Task not found")
    return _public_task_payload(task_id)


@app.get("/api/analysis/tasks")
async def list_tasks(api_key: Optional[str] = Header(None)):
    """List all tasks (active and recent)"""
    if not _check_api_key(api_key):
        _auth_error()
    tasks = [_public_task_summary(task_id) for task_id in app.state.task_results]
    # Sort by created_at descending (most recent first)
    tasks.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return {"contract_version": "v1alpha1", "tasks": tasks, "total": len(tasks)}


@app.delete("/api/analysis/cancel/{task_id}")
async def cancel_task(task_id: str, api_key: Optional[str] = Header(None)):
    """Cancel a running task."""
    if not _check_api_key(api_key):
        _auth_error()
    if task_id not in app.state.task_results:
        raise HTTPException(status_code=404, detail="Task not found")

    proc = app.state.processes.get(task_id)
    if proc and proc.returncode is None:
        try:
            proc.kill()
        except Exception:
            pass

    task = app.state.analysis_tasks.get(task_id)
    if task:
        task.cancel()

    state = app.state.job_service.cancel_job(task_id, error="用户取消")
    if state is not None:
        state["status"] = "cancelled"
        state["error"] = {
            "code": "cancelled",
            "message": "用户取消",
            "retryable": False,
        }
        app.state.result_store.save_task_status(task_id, state)
        await broadcast_progress(task_id, state)
    app.state.result_store.delete_task_status(task_id)

    return {"contract_version": "v1alpha1", "task_id": task_id, "status": "cancelled"}


# ============== WebSocket ==============

@app.websocket("/ws/analysis/{task_id}")
async def websocket_analysis(websocket: WebSocket, task_id: str):
    """WebSocket for real-time analysis progress. Auth via ?api_key= query param."""
    # Optional API key check for WebSocket
    ws_api_key = websocket.query_params.get("api_key")
    if not _check_api_key(ws_api_key):
        await websocket.close(code=4001, reason="Unauthorized")
        return
    await websocket.accept()

    if task_id not in app.state.active_connections:
        app.state.active_connections[task_id] = []
    app.state.active_connections[task_id].append(websocket)

    # Send current state immediately if available
    if task_id in app.state.task_results:
        await websocket.send_text(json.dumps({
            "type": "progress",
            **_public_task_payload(task_id)
        }))

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            if message.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        if task_id in app.state.active_connections:
            app.state.active_connections[task_id].remove(websocket)


async def broadcast_progress(task_id: str, progress: dict):
    """Broadcast progress to all connections for a task"""
    if task_id not in app.state.active_connections:
        return

    payload = _public_task_payload(task_id, state_override=progress)
    message = json.dumps({"type": "progress", **payload})
    dead = []

    for connection in app.state.active_connections[task_id]:
        try:
            await connection.send_text(message)
        except Exception:
            dead.append(connection)

    for conn in dead:
        app.state.active_connections[task_id].remove(conn)


def _load_task_contract(task_id: str, state: Optional[dict] = None) -> Optional[dict]:
    current_state = state or app.state.task_results.get(task_id)
    if current_state is None:
        return None
    return app.state.result_store.load_result_contract(
        result_ref=current_state.get("result_ref"),
        task_id=task_id,
    )


def _public_task_payload(task_id: str, state_override: Optional[dict] = None) -> dict:
    state = state_override or app.state.task_results[task_id]
    contract = _load_task_contract(task_id, state)
    return app.state.job_service.to_public_task_payload(task_id, contract=contract)


def _public_task_summary(task_id: str, state_override: Optional[dict] = None) -> dict:
    state = state_override or app.state.task_results[task_id]
    contract = _load_task_contract(task_id, state)
    return app.state.job_service.to_task_summary(task_id, contract=contract)


# ============== Reports ==============

def get_results_dir() -> Path:
    return Path(__file__).parent.parent.parent / "results"


def get_reports_list():
    """Get all historical reports"""
    results_dir = get_results_dir()
    reports = []
    if not results_dir.exists():
        return reports
    for ticker_dir in results_dir.iterdir():
        if ticker_dir.is_dir() and ticker_dir.name != "TradingAgentsStrategy_logs":
            ticker = ticker_dir.name
            for date_dir in ticker_dir.iterdir():
                # Skip non-date directories like TradingAgentsStrategy_logs
                if date_dir.is_dir() and date_dir.name.startswith("20"):
                    reports.append({
                        "ticker": ticker,
                        "date": date_dir.name,
                        "path": str(date_dir)
                    })
    return sorted(reports, key=lambda x: x["date"], reverse=True)


def get_report_content(ticker: str, date: str) -> Optional[dict]:
    """Get report content for a specific ticker and date"""
    # Validate inputs to prevent path traversal
    if ".." in ticker or "/" in ticker or "\\" in ticker:
        return None
    if ".." in date or "/" in date or "\\" in date:
        return None
    report_dir = get_results_dir() / ticker / date
    # Strict traversal check: resolved path must be within get_results_dir()
    try:
        report_dir.resolve().relative_to(get_results_dir().resolve())
    except ValueError:
        return None
    if not report_dir.exists():
        return None
    content = {}
    complete_report = report_dir / "complete_report.md"
    if complete_report.exists():
        content["report"] = complete_report.read_text()
    for stage in ["1_analysts", "2_research", "3_trading", "4_risk", "5_portfolio"]:
        stage_dir = report_dir / "reports" / stage
        if stage_dir.exists():
            for f in stage_dir.glob("*.md"):
                content[f.name] = f.read_text()
    return content


@app.get("/api/reports/list")
async def list_reports(
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    api_key: Optional[str] = Header(None),
):
    if not _check_api_key(api_key):
        _auth_error()
    reports = get_reports_list()
    total = len(reports)
    return {
        "reports": sorted(reports, key=lambda x: x["date"], reverse=True)[offset : offset + limit],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/reports/{ticker}/{date}")
async def get_report(ticker: str, date: str, api_key: Optional[str] = Header(None)):
    if not _check_api_key(api_key):
        _auth_error()
    content = get_report_content(ticker, date)
    if not content:
        raise HTTPException(status_code=404, detail="Report not found")
    return content


# ============== Report Export ==============

import csv
import io
import re
from fpdf import FPDF


def _extract_decision(markdown_text: str) -> str:
    """Extract BUY/OVERWEIGHT/SELL/UNDERWEIGHT/HOLD from markdown bold text."""
    match = re.search(r'\*\*(BUY|SELL|HOLD|OVERWEIGHT|UNDERWEIGHT)\*\*', markdown_text)
    return match.group(1) if match else 'UNKNOWN'


def _extract_summary(markdown_text: str) -> str:
    """Extract first ~200 chars after '## 分析摘要'."""
    match = re.search(r'## 分析摘要\s*\n+(.{0,300}?)(?=\n##|\Z)', markdown_text, re.DOTALL)
    if match:
        text = match.group(1).strip()
        # Strip markdown formatting
        text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
        text = re.sub(r'\*(.*?)\*', r'\1', text)
        text = re.sub(r'[#\n]+', ' ', text)
        return text[:200].strip()
    return ''


@app.get("/api/reports/export")
async def export_reports_csv(
    api_key: Optional[str] = Header(None),
):
    """Export all reports as CSV: ticker,date,decision,summary."""
    if not _check_api_key(api_key):
        _auth_error()
    reports = get_reports_list()
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["ticker", "date", "decision", "summary"])
    writer.writeheader()
    for r in reports:
        content = get_report_content(r["ticker"], r["date"])
        if content and content.get("report"):
            writer.writerow({
                "ticker": r["ticker"],
                "date": r["date"],
                "decision": _extract_decision(content["report"]),
                "summary": _extract_summary(content["report"]),
            })
        else:
            writer.writerow({
                "ticker": r["ticker"],
                "date": r["date"],
                "decision": "UNKNOWN",
                "summary": "",
            })
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=tradingagents_reports.csv"},
    )


@app.get("/api/reports/{ticker}/{date}/pdf")
async def export_report_pdf(ticker: str, date: str, api_key: Optional[str] = Header(None)):
    """Export a single report as PDF."""
    if not _check_api_key(api_key):
        _auth_error()
    content = get_report_content(ticker, date)
    if not content or not content.get("report"):
        raise HTTPException(status_code=404, detail="Report not found")

    markdown_text = content["report"]
    decision = _extract_decision(markdown_text)
    summary = _extract_summary(markdown_text)

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=20)

    # Try multiple font paths for cross-platform support
    font_paths = [
        "/System/Library/Fonts/Supplemental/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        str(Path.home() / ".local/share/fonts/DejaVuSans.ttf"),
        str(Path.home() / ".fonts/DejaVuSans.ttf"),
    ]
    regular_font = None
    bold_font = None
    for p in font_paths:
        if Path(p).exists():
            if "Bold" in p and bold_font is None:
                bold_font = p
            elif regular_font is None and "Bold" not in p:
                regular_font = p

    use_dejavu = bool(regular_font and bold_font)
    if use_dejavu:
        pdf.add_font("DejaVu", "", regular_font, unicode=True)
        pdf.add_font("DejaVu", "B", bold_font, unicode=True)
        font_regular = "DejaVu"
        font_bold = "DejaVu"
    else:
        font_regular = "Helvetica"
        font_bold = "Helvetica"

    pdf.add_page()
    pdf.set_font(font_bold, "B", 18)
    pdf.cell(0, 12, f"TradingAgents 分析报告", ln=True, align="C")
    pdf.ln(5)

    pdf.set_font(font_regular, "", 11)
    pdf.cell(0, 8, f"股票: {ticker}    日期: {date}", ln=True)
    pdf.ln(3)

    # Decision badge
    pdf.set_font(font_bold, "B", 14)
    if decision == "BUY":
        pdf.set_text_color(34, 197, 94)
    elif decision == "OVERWEIGHT":
        pdf.set_text_color(134, 239, 172)
    elif decision == "SELL":
        pdf.set_text_color(220, 38, 38)
    elif decision == "UNDERWEIGHT":
        pdf.set_text_color(252, 165, 165)
    else:
        pdf.set_text_color(245, 158, 11)
    pdf.cell(0, 10, f"决策: {decision}", ln=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(5)

    # Summary
    pdf.set_font(font_bold, "B", 12)
    pdf.cell(0, 8, "分析摘要", ln=True)
    pdf.set_font(font_regular, "", 10)
    pdf.multi_cell(0, 6, summary or "无")
    pdf.ln(5)

    # Full report text (stripped of heavy markdown)
    pdf.set_font(font_bold, "B", 12)
    pdf.cell(0, 8, "完整报告", ln=True)
    pdf.set_font(font_regular, "", 9)
    # Split into lines, filter out very long lines
    for line in markdown_text.splitlines():
        line = re.sub(r'\*\*(.*?)\*\*', r'\1', line)
        line = re.sub(r'\*(.*?)\*', r'\1', line)
        line = re.sub(r'#{1,6} ', '', line)
        line = line.strip()
        if not line:
            pdf.ln(2)
            continue
        if len(line) > 120:
            line = line[:120] + "..."
        try:
            pdf.multi_cell(0, 5, line)
        except Exception:
            pass

    return Response(
        content=pdf.output(),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={ticker}_{date}_report.pdf"},
    )


# ============== Portfolio ==============

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from api.portfolio import (
    create_legacy_portfolio_gateway,
    get_watchlist, add_to_watchlist, remove_from_watchlist,
    get_positions, add_position, remove_position,
    get_accounts, create_account, delete_account,
)


# --- Watchlist ---

@app.get("/api/portfolio/watchlist")
async def list_watchlist(api_key: Optional[str] = Header(None)):
    if not _check_api_key(api_key):
        _auth_error()
    return {"watchlist": get_watchlist()}


@app.post("/api/portfolio/watchlist")
async def create_watchlist_entry(body: dict, api_key: Optional[str] = Header(None)):
    if not _check_api_key(api_key):
        _auth_error()
    try:
        entry = add_to_watchlist(body["ticker"], body.get("name", body["ticker"]))
        return entry
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/portfolio/watchlist/{ticker}")
async def delete_watchlist_entry(ticker: str, api_key: Optional[str] = Header(None)):
    if not _check_api_key(api_key):
        _auth_error()
    if remove_from_watchlist(ticker):
        return {"ok": True}
    raise HTTPException(status_code=404, detail="Ticker not found in watchlist")


# --- Accounts ---

@app.get("/api/portfolio/accounts")
async def list_accounts(api_key: Optional[str] = Header(None)):
    if not _check_api_key(api_key):
        _auth_error()
    accounts = get_accounts()
    return {"accounts": list(accounts.get("accounts", {}).keys())}


@app.post("/api/portfolio/accounts")
async def create_account_endpoint(body: dict, api_key: Optional[str] = Header(None)):
    if not _check_api_key(api_key):
        _auth_error()
    try:
        return create_account(body["account_name"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/portfolio/accounts/{account_name}")
async def delete_account_endpoint(account_name: str, api_key: Optional[str] = Header(None)):
    if not _check_api_key(api_key):
        _auth_error()
    if delete_account(account_name):
        return {"ok": True}
    raise HTTPException(status_code=404, detail="Account not found")


# --- Positions ---

@app.get("/api/portfolio/positions")
async def list_positions(account: Optional[str] = Query(None), api_key: Optional[str] = Header(None)):
    if not _check_api_key(api_key):
        _auth_error()
    if app.state.migration_flags.use_result_store:
        return {"positions": await app.state.result_store.get_positions(account)}
    return {"positions": await get_positions(account)}


@app.post("/api/portfolio/positions")
async def create_position(body: dict, api_key: Optional[str] = Header(None)):
    if not _check_api_key(api_key):
        _auth_error()
    try:
        pos = add_position(
            ticker=body["ticker"],
            shares=body["shares"],
            cost_price=body["cost_price"],
            purchase_date=body.get("purchase_date"),
            notes=body.get("notes", ""),
            account=body.get("account", "默认账户"),
        )
        return pos
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/portfolio/positions/{ticker}")
async def delete_position(ticker: str, position_id: Optional[str] = Query(None), account: Optional[str] = Query(None), api_key: Optional[str] = Header(None)):
    if not _check_api_key(api_key):
        _auth_error()
    removed = remove_position(ticker, position_id or "", account)
    if removed:
        return {"ok": True}
    raise HTTPException(status_code=404, detail="Position not found")


@app.get("/api/portfolio/positions/export")
async def export_positions_csv(account: Optional[str] = Query(None), api_key: Optional[str] = Header(None)):
    if not _check_api_key(api_key):
        _auth_error()
    if app.state.migration_flags.use_result_store:
        positions = await app.state.result_store.get_positions(account)
    else:
        positions = await get_positions(account)
    import csv
    import io
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["ticker", "shares", "cost_price", "purchase_date", "notes", "account"])
    writer.writeheader()
    for p in positions:
        writer.writerow({k: p[k] for k in ["ticker", "shares", "cost_price", "purchase_date", "notes", "account"]})
    return Response(content=output.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=positions.csv"})


# --- Recommendations ---

@app.get("/api/portfolio/recommendations")
async def list_recommendations(
    date: Optional[str] = Query(None),
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    api_key: Optional[str] = Header(None),
):
    if not _check_api_key(api_key):
        _auth_error()
    return app.state.result_store.get_recommendations(date, limit, offset)


@app.get("/api/portfolio/recommendations/{date}/{ticker}")
async def get_recommendation_endpoint(date: str, ticker: str, api_key: Optional[str] = Header(None)):
    if not _check_api_key(api_key):
        _auth_error()
    rec = app.state.result_store.get_recommendation(date, ticker)
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    return rec


# --- Batch Analysis ---

@app.post("/api/portfolio/analyze")
async def start_portfolio_analysis(
    http_request: Request,
    api_key: Optional[str] = Header(None),
):
    """Trigger batch analysis for all watchlist tickers."""
    if not _check_api_key(api_key):
        _auth_error()

    import uuid

    date = datetime.now().strftime("%Y-%m-%d")
    task_id = f"port_{date}_{uuid.uuid4().hex[:6]}"
    request_context = build_request_context(http_request, api_key=api_key)

    try:
        return await app.state.analysis_service.start_portfolio_analysis(
            task_id=task_id,
            date=date,
            request_context=request_context,
            broadcast_progress=broadcast_progress,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))



@app.get("/")
async def root():
    # Production mode: serve the built React frontend
    frontend_dist = Path(__file__).parent.parent / "frontend" / "dist" / "index.html"
    if frontend_dist.exists():
        return FileResponse(str(frontend_dist))
    return {"message": "TradingAgents Web Dashboard API", "version": "0.1.0"}


@app.websocket("/ws/orchestrator")
async def ws_orchestrator(websocket: WebSocket, api_key: Optional[str] = None):
    """WebSocket endpoint for orchestrator live signals."""
    # Auth check before accepting — reject unauthenticated connections
    if not _check_api_key(api_key):
        await websocket.close(code=4401)
        return

    import sys
    sys.path.insert(0, str(REPO_ROOT))
    from orchestrator.config import OrchestratorConfig
    from orchestrator.orchestrator import TradingOrchestrator
    from orchestrator.live_mode import LiveMode

    config = OrchestratorConfig(
        quant_backtest_path=os.environ.get("QUANT_BACKTEST_PATH", ""),
    )
    orchestrator = TradingOrchestrator(config)
    live = LiveMode(orchestrator)

    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)
            tickers = payload.get("tickers", [])
            date = payload.get("date")

            results = await live.run_once(tickers, date)
            await websocket.send_text(json.dumps({
                "contract_version": "v1alpha1",
                "signals": results,
            }))
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_text(json.dumps({"error": str(e)}))
        except Exception:
            pass


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    # Production mode: serve the built React frontend
    frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
    if frontend_dist.exists():
        app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")
    uvicorn.run(app, host=host, port=port)
