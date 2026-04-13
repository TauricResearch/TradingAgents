"""
TradingAgents Web Dashboard Backend
FastAPI REST API + WebSocket for real-time analysis progress
"""
import asyncio
import hmac
import json
import os
import subprocess
import sys
import tempfile
import time
import traceback
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
        analysis_python=ANALYSIS_PYTHON,
        repo_root=REPO_ROOT,
        analysis_script_template=ANALYSIS_SCRIPT_TEMPLATE,
        api_key_resolver=_get_analysis_api_key,
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


def _save_task_status(task_id: str, data: dict):
    """Persist task state to disk"""
    try:
        TASK_STATUS_DIR.mkdir(parents=True, exist_ok=True)
        (TASK_STATUS_DIR / f"{task_id}.json").write_text(json.dumps(data, ensure_ascii=False))
    except Exception:
        pass


def _delete_task_status(task_id: str):
    """Remove persisted task state from disk"""
    try:
        (TASK_STATUS_DIR / f"{task_id}.json").unlink(missing_ok=True)
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

# Script template for subprocess-based analysis
# api_key is passed via environment variable (not CLI) for security
ANALYSIS_SCRIPT_TEMPLATE = """
import sys
import os
import json
ticker = sys.argv[1]
date = sys.argv[2]
repo_root = sys.argv[3]

sys.path.insert(0, repo_root)
os.environ["ANTHROPIC_BASE_URL"] = "https://api.minimaxi.com/anthropic"
import py_mini_racer
sys.modules["mini_racer"] = py_mini_racer
from pathlib import Path

print("STAGE:analysts", flush=True)

from orchestrator.config import OrchestratorConfig
from orchestrator.orchestrator import TradingOrchestrator

config = OrchestratorConfig(
    quant_backtest_path=os.environ.get("QUANT_BACKTEST_PATH", ""),
    trading_agents_config={
        "llm_provider": "anthropic",
        "deep_think_llm": "MiniMax-M2.7-highspeed",
        "quick_think_llm": "MiniMax-M2.7-highspeed",
        "backend_url": "https://api.minimaxi.com/anthropic",
        "max_debate_rounds": 1,
        "max_risk_discuss_rounds": 1,
        "project_dir": os.path.join(repo_root, "tradingagents"),
        "results_dir": os.path.join(repo_root, "results"),
    }
)

print("STAGE:research", flush=True)

orchestrator = TradingOrchestrator(config)

print("STAGE:trading", flush=True)

try:
    result = orchestrator.get_combined_signal(ticker, date)
except ValueError as _e:
    print("ANALYSIS_ERROR:" + str(_e), file=sys.stderr, flush=True)
    sys.exit(1)

print("STAGE:risk", flush=True)

# Map direction + confidence to 5-level signal
# FinalSignal is a dataclass, access via attributes not .get()
direction = result.direction
confidence = result.confidence
llm_sig_obj = result.llm_signal
quant_sig_obj = result.quant_signal
# LLM metadata has "rating" field; quant metadata does not — derive from direction
llm_signal = llm_sig_obj.metadata.get("rating", "HOLD") if llm_sig_obj else "HOLD"
if quant_sig_obj is None:
    quant_signal = "HOLD"
elif quant_sig_obj.direction == 1:
    quant_signal = "BUY" if quant_sig_obj.confidence >= 0.7 else "OVERWEIGHT"
elif quant_sig_obj.direction == -1:
    quant_signal = "SELL" if quant_sig_obj.confidence >= 0.7 else "UNDERWEIGHT"
else:
    quant_signal = "HOLD"

if direction == 1:
    signal = "BUY" if confidence >= 0.7 else "OVERWEIGHT"
elif direction == -1:
    signal = "SELL" if confidence >= 0.7 else "UNDERWEIGHT"
else:
    signal = "HOLD"

results_dir = Path(repo_root) / "results" / ticker / date
results_dir.mkdir(parents=True, exist_ok=True)

report_content = (
    "# TradingAgents 分析报告\\n\\n"
    "**股票**: " + ticker + "\\n"
    "**日期**: " + date + "\\n\\n"
    "## 最终决策\\n\\n"
    "**" + signal + "**\\n\\n"
    "## 信号详情\\n\\n"
    "- LLM 信号: " + llm_signal + "\\n"
    "- Quant 信号: " + quant_signal + "\\n"
    "- 置信度: " + f"{confidence:.1%}" + "\\n\\n"
    "## 分析摘要\\n\\n"
    "N/A\\n"
)

report_path = results_dir / "complete_report.md"
report_path.write_text(report_content)

print("STAGE:portfolio", flush=True)
signal_detail = json.dumps({"llm_signal": llm_signal, "quant_signal": quant_signal, "confidence": confidence})
print("SIGNAL_DETAIL:" + signal_detail, flush=True)
print("ANALYSIS_COMPLETE:" + signal, flush=True)
"""


@app.post("/api/analysis/start")
async def start_analysis(request: AnalysisRequest, api_key: Optional[str] = Header(None)):
    """Start a new analysis task"""
    import uuid
    task_id = f"{request.ticker}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    date = request.date or datetime.now().strftime("%Y-%m-%d")

    # Check dashboard API key (opt-in auth)
    if not _check_api_key(api_key):
        _auth_error()

    # Validate ANTHROPIC_API_KEY for the analysis subprocess
    anthropic_key = _get_analysis_api_key()
    if not anthropic_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY environment variable not set")

    # Initialize task state
    app.state.task_results[task_id] = {
        "task_id": task_id,
        "ticker": request.ticker,
        "date": date,
        "status": "running",
        "progress": 0,
        "current_stage": "analysts",
        "created_at": datetime.now().isoformat(),
        "elapsed": 0,
        "stages": [
            {"status": "running", "completed_at": None},
            {"status": "pending", "completed_at": None},
            {"status": "pending", "completed_at": None},
            {"status": "pending", "completed_at": None},
            {"status": "pending", "completed_at": None},
        ],
        "logs": [],
        "decision": None,
        "quant_signal": None,
        "llm_signal": None,
        "confidence": None,
        "error": None,
    }
    await broadcast_progress(task_id, app.state.task_results[task_id])

    # Write analysis script to temp file with restrictive permissions (avoids subprocess -c quoting issues)
    fd, script_path_str = tempfile.mkstemp(suffix=".py", prefix=f"analysis_{task_id}_")
    script_path = Path(script_path_str)
    os.chmod(script_path, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(ANALYSIS_SCRIPT_TEMPLATE)

    # Store process reference for cancellation
    app.state.processes = getattr(app.state, 'processes', {})
    app.state.processes[task_id] = None

    # Cancellation event for the monitor coroutine
    cancel_event = asyncio.Event()

    # Stage name to index mapping
    STAGE_NAMES = ["analysts", "research", "trading", "risk", "portfolio"]

    def _update_task_stage(stage_name: str):
        """Update task state for a completed stage and mark next as running."""
        try:
            idx = STAGE_NAMES.index(stage_name)
        except ValueError:
            return
        # Mark all previous stages as completed
        for i in range(idx):
            if app.state.task_results[task_id]["stages"][i]["status"] != "completed":
                app.state.task_results[task_id]["stages"][i]["status"] = "completed"
                app.state.task_results[task_id]["stages"][i]["completed_at"] = datetime.now().strftime("%H:%M:%S")
        # Mark current as completed
        if app.state.task_results[task_id]["stages"][idx]["status"] != "completed":
            app.state.task_results[task_id]["stages"][idx]["status"] = "completed"
            app.state.task_results[task_id]["stages"][idx]["completed_at"] = datetime.now().strftime("%H:%M:%S")
        # Mark next as running
        if idx + 1 < 5:
            if app.state.task_results[task_id]["stages"][idx + 1]["status"] == "pending":
                app.state.task_results[task_id]["stages"][idx + 1]["status"] = "running"
        # Update progress
        app.state.task_results[task_id]["progress"] = int((idx + 1) / 5 * 100)
        app.state.task_results[task_id]["current_stage"] = stage_name

    async def run_analysis():
        """Run analysis subprocess and broadcast progress"""
        try:
            # Use clean environment - don't inherit parent env
            clean_env = {k: v for k, v in os.environ.items()
                        if not k.startswith(("PYTHON", "CONDA", "VIRTUAL"))}
            clean_env["ANTHROPIC_API_KEY"] = anthropic_key
            clean_env["ANTHROPIC_BASE_URL"] = "https://api.minimaxi.com/anthropic"

            proc = await asyncio.create_subprocess_exec(
                str(ANALYSIS_PYTHON),
                str(script_path),
                request.ticker,
                date,
                str(REPO_ROOT),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=clean_env,
            )
            app.state.processes[task_id] = proc

            # Read stdout line-by-line for real-time stage updates
            stdout_lines = []
            while True:
                try:
                    line_bytes = await asyncio.wait_for(proc.stdout.readline(), timeout=300.0)
                except asyncio.TimeoutError:
                    break
                if not line_bytes:
                    break
                line = line_bytes.decode(errors="replace").rstrip()
                stdout_lines.append(line)
                if line.startswith("STAGE:"):
                    stage = line.split(":", 1)[1].strip()
                    _update_task_stage(stage)
                    await broadcast_progress(task_id, app.state.task_results[task_id])
                if cancel_event.is_set():
                    break

            await proc.wait()
            stderr_bytes = await proc.stderr.read()

            # Clean up script file
            try:
                script_path.unlink()
            except Exception:
                pass

            if proc.returncode == 0:
                output = "\n".join(stdout_lines)
                decision = "HOLD"
                for line in stdout_lines:
                    if line.startswith("SIGNAL_DETAIL:"):
                        try:
                            detail = json.loads(line.split(":", 1)[1].strip())
                            app.state.task_results[task_id]["quant_signal"] = detail.get("quant_signal")
                            app.state.task_results[task_id]["llm_signal"] = detail.get("llm_signal")
                            app.state.task_results[task_id]["confidence"] = detail.get("confidence")
                        except Exception:
                            pass
                    if line.startswith("ANALYSIS_COMPLETE:"):
                        decision = line.split(":", 1)[1].strip()

                app.state.task_results[task_id]["status"] = "completed"
                app.state.task_results[task_id]["progress"] = 100
                app.state.task_results[task_id]["decision"] = decision
                app.state.task_results[task_id]["current_stage"] = "portfolio"
                for i in range(5):
                    app.state.task_results[task_id]["stages"][i]["status"] = "completed"
                    if not app.state.task_results[task_id]["stages"][i].get("completed_at"):
                        app.state.task_results[task_id]["stages"][i]["completed_at"] = datetime.now().strftime("%H:%M:%S")
            else:
                error_msg = stderr_bytes.decode(errors="replace")[-1000:] if stderr_bytes else "Unknown error"
                app.state.task_results[task_id]["status"] = "failed"
                app.state.task_results[task_id]["error"] = error_msg

            _save_task_status(task_id, app.state.task_results[task_id])

        except Exception as e:
            cancel_event.set()
            app.state.task_results[task_id]["status"] = "failed"
            app.state.task_results[task_id]["error"] = str(e)
            try:
                script_path.unlink()
            except Exception:
                pass

            _save_task_status(task_id, app.state.task_results[task_id])

        await broadcast_progress(task_id, app.state.task_results[task_id])

    task = asyncio.create_task(run_analysis())
    app.state.analysis_tasks[task_id] = task

    return {
        "task_id": task_id,
        "ticker": request.ticker,
        "date": date,
        "status": "running",
    }


@app.get("/api/analysis/status/{task_id}")
async def get_task_status(task_id: str, api_key: Optional[str] = Header(None)):
    """Get task status"""
    if not _check_api_key(api_key):
        _auth_error()
    if task_id not in app.state.task_results:
        raise HTTPException(status_code=404, detail="Task not found")
    return app.state.task_results[task_id]


@app.get("/api/analysis/tasks")
async def list_tasks(api_key: Optional[str] = Header(None)):
    """List all tasks (active and recent)"""
    if not _check_api_key(api_key):
        _auth_error()
    tasks = []
    for task_id, state in app.state.task_results.items():
        tasks.append({
            "task_id": task_id,
            "ticker": state.get("ticker"),
            "date": state.get("date"),
            "status": state.get("status"),
            "progress": state.get("progress", 0),
            "decision": state.get("decision"),
            "error": state.get("error"),
            "created_at": state.get("created_at"),
        })
    # Sort by created_at descending (most recent first)
    tasks.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return {"tasks": tasks, "total": len(tasks)}


@app.delete("/api/analysis/cancel/{task_id}")
async def cancel_task(task_id: str, api_key: Optional[str] = Header(None)):
    """Cancel a running task"""
    if not _check_api_key(api_key):
        _auth_error()
    if task_id not in app.state.task_results:
        raise HTTPException(status_code=404, detail="Task not found")

    # Kill the subprocess if it's still running
    proc = app.state.processes.get(task_id)
    if proc and proc.returncode is None:
        try:
            proc.kill()
        except Exception:
            pass

    # Cancel the asyncio task
    task = app.state.analysis_tasks.get(task_id)
    if task:
        task.cancel()
        app.state.task_results[task_id]["status"] = "failed"
        app.state.task_results[task_id]["error"] = "用户取消"
        _save_task_status(task_id, app.state.task_results[task_id])
        await broadcast_progress(task_id, app.state.task_results[task_id])

    # Clean up temp script (may use tempfile.mkstemp with random suffix)
    for p in Path("/tmp").glob(f"analysis_{task_id}_*.py"):
        try:
            p.unlink()
        except Exception:
            pass

    # Remove persisted task state
    _delete_task_status(task_id)

    return {"task_id": task_id, "status": "cancelled"}


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
            **app.state.task_results[task_id]
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

    message = json.dumps({"type": "progress", **progress})
    dead = []

    for connection in app.state.active_connections[task_id]:
        try:
            await connection.send_text(message)
        except Exception:
            dead.append(connection)

    for conn in dead:
        app.state.active_connections[task_id].remove(conn)


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
    get_recommendations, get_recommendation, save_recommendation,
    RECOMMENDATIONS_DIR,
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
    return get_recommendations(date, limit, offset)


@app.get("/api/portfolio/recommendations/{date}/{ticker}")
async def get_recommendation_endpoint(date: str, ticker: str, api_key: Optional[str] = Header(None)):
    if not _check_api_key(api_key):
        _auth_error()
    rec = get_recommendation(date, ticker)
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    return rec


# --- Batch Analysis ---

@app.post("/api/portfolio/analyze")
async def start_portfolio_analysis(api_key: Optional[str] = Header(None)):
    """
    Trigger batch analysis for all watchlist tickers.
    Runs serially, streaming progress via WebSocket (task_id prefixed with 'port_').
    """
    if not _check_api_key(api_key):
        _auth_error()
    import uuid
    date = datetime.now().strftime("%Y-%m-%d")
    task_id = f"port_{date}_{uuid.uuid4().hex[:6]}"

    if app.state.migration_flags.use_application_services:
        request_context = build_request_context(api_key=api_key)
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

    watchlist = get_watchlist()
    if not watchlist:
        raise HTTPException(status_code=400, detail="自选股为空，请先添加股票")

    total = len(watchlist)
    app.state.task_results[task_id] = {
        "task_id": task_id,
        "type": "portfolio",
        "status": "running",
        "total": total,
        "completed": 0,
        "failed": 0,
        "current_ticker": None,
        "results": [],
        "error": None,
    }

    api_key = _get_analysis_api_key()
    if not api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY environment variable not set")

    await broadcast_progress(task_id, app.state.task_results[task_id])

    async def run_portfolio_analysis():
        max_retries = MAX_RETRY_COUNT

        async def run_single_analysis(ticker: str, stock: dict) -> tuple[bool, str, dict | None]:
            """Run analysis for one ticker. Returns (success, decision, rec_or_error)."""
            last_error = None
            for attempt in range(max_retries + 1):
                script_path = None
                try:
                    fd, script_path_str = tempfile.mkstemp(suffix=".py", prefix=f"analysis_{task_id}_{stock['_idx']}_")
                    script_path = Path(script_path_str)
                    os.chmod(script_path, 0o600)
                    with os.fdopen(fd, "w") as f:
                        f.write(ANALYSIS_SCRIPT_TEMPLATE)

                    clean_env = {k: v for k, v in os.environ.items()
                                if not k.startswith(("PYTHON", "CONDA", "VIRTUAL"))}
                    clean_env["ANTHROPIC_API_KEY"] = api_key
                    clean_env["ANTHROPIC_BASE_URL"] = "https://api.minimaxi.com/anthropic"

                    proc = await asyncio.create_subprocess_exec(
                        str(ANALYSIS_PYTHON), str(script_path), ticker, date, str(REPO_ROOT),
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                        env=clean_env,
                    )
                    app.state.processes[task_id] = proc

                    stdout, stderr = await proc.communicate()

                    try:
                        script_path.unlink()
                    except Exception:
                        pass

                    if proc.returncode == 0:
                        output = stdout.decode()
                        decision = "HOLD"
                        quant_signal = None
                        llm_signal = None
                        confidence = None
                        for line in output.splitlines():
                            if line.startswith("SIGNAL_DETAIL:"):
                                try:
                                    detail = json.loads(line.split(":", 1)[1].strip())
                                    quant_signal = detail.get("quant_signal")
                                    llm_signal = detail.get("llm_signal")
                                    confidence = detail.get("confidence")
                                except Exception:
                                    pass
                            if line.startswith("ANALYSIS_COMPLETE:"):
                                decision = line.split(":", 1)[1].strip()
                        rec = {
                            "ticker": ticker,
                            "name": stock.get("name", ticker),
                            "analysis_date": date,
                            "decision": decision,
                            "quant_signal": quant_signal,
                            "llm_signal": llm_signal,
                            "confidence": confidence,
                            "created_at": datetime.now().isoformat(),
                        }
                        save_recommendation(date, ticker, rec)
                        return True, decision, rec
                    else:
                        last_error = stderr.decode()[-500:] if stderr else f"exit {proc.returncode}"
                except Exception as e:
                    last_error = str(e)
                finally:
                    if script_path:
                        try:
                            script_path.unlink()
                        except Exception:
                            pass
                if attempt < max_retries:
                    await asyncio.sleep(RETRY_BASE_DELAY_SECS ** attempt)  # exponential backoff: 1s, 2s

            return False, "HOLD", None

        try:
            for i, stock in enumerate(watchlist):
                stock["_idx"] = i  # used in temp file name
                ticker = stock["ticker"]
                app.state.task_results[task_id]["current_ticker"] = ticker
                app.state.task_results[task_id]["status"] = "running"
                app.state.task_results[task_id]["completed"] = i
                await broadcast_progress(task_id, app.state.task_results[task_id])

                success, decision, rec = await run_single_analysis(ticker, stock)
                if success:
                    app.state.task_results[task_id]["completed"] = i + 1
                    app.state.task_results[task_id]["results"].append(rec)
                else:
                    app.state.task_results[task_id]["failed"] += 1

                await broadcast_progress(task_id, app.state.task_results[task_id])

            app.state.task_results[task_id]["status"] = "completed"
            app.state.task_results[task_id]["current_ticker"] = None
            _save_task_status(task_id, app.state.task_results[task_id])

        except Exception as e:
            app.state.task_results[task_id]["status"] = "failed"
            app.state.task_results[task_id]["error"] = str(e)
            _save_task_status(task_id, app.state.task_results[task_id])

        await broadcast_progress(task_id, app.state.task_results[task_id])

    task = asyncio.create_task(run_portfolio_analysis())
    app.state.analysis_tasks[task_id] = task

    return {
        "task_id": task_id,
        "total": total,
        "status": "running",
    }



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
            await websocket.send_text(json.dumps({"signals": results}))
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
