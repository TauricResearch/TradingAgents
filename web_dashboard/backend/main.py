"""
TradingAgents Web Dashboard Backend
FastAPI REST API + WebSocket for real-time analysis progress
"""
import asyncio
import fcntl
import json
import os
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Path to TradingAgents repo root
REPO_ROOT = Path(__file__).parent.parent.parent
# Use the currently running Python interpreter
ANALYSIS_PYTHON = Path(sys.executable)


# ============== Lifespan ==============

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    app.state.active_connections: dict[str, list[WebSocket]] = {}
    app.state.task_results: dict[str, dict] = {}
    app.state.analysis_tasks: dict[str, asyncio.Task] = {}
    yield


# ============== App ==============

app = FastAPI(
    title="TradingAgents Web Dashboard API",
    version="0.1.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============== Pydantic Models ==============

class AnalysisRequest(BaseModel):
    ticker: str
    date: Optional[str] = None

class ScreenRequest(BaseModel):
    mode: str = "china_strict"


# ============== Cache Helpers ==============

CACHE_DIR = Path(__file__).parent.parent / "cache"
CACHE_TTL_SECONDS = 300  # 5 minutes


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
async def screen_stocks(mode: str = Query("china_strict"), refresh: bool = Query(False)):
    """Screen stocks using SEPA criteria with caching"""
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
ticker = sys.argv[1]
date = sys.argv[2]
repo_root = sys.argv[3]

sys.path.insert(0, repo_root)
os.environ["ANTHROPIC_BASE_URL"] = "https://api.minimaxi.com/anthropic"
import py_mini_racer
sys.modules["mini_racer"] = py_mini_racer
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from pathlib import Path

print("STAGE:analysts", flush=True)

config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "anthropic"
config["deep_think_llm"] = "MiniMax-M2.7-highspeed"
config["quick_think_llm"] = "MiniMax-M2.7-highspeed"
config["backend_url"] = "https://api.minimaxi.com/anthropic"
config["max_debate_rounds"] = 1
config["max_risk_discuss_rounds"] = 1

print("STAGE:research", flush=True)

ta = TradingAgentsGraph(debug=False, config=config)
print("STAGE:trading", flush=True)

final_state, decision = ta.propagate(ticker, date)

print("STAGE:risk", flush=True)

results_dir = Path(repo_root) / "results" / ticker / date
results_dir.mkdir(parents=True, exist_ok=True)

signal = decision if isinstance(decision, str) else decision.get("signal", "HOLD")
report_content = (
    "# TradingAgents 分析报告\\n\\n"
    "**股票**: " + ticker + "\\n"
    "**日期**: " + date + "\\n\\n"
    "## 最终决策\\n\\n"
    "**" + signal + "**\\n\\n"
    "## 分析摘要\\n\\n"
    + final_state.get("market_report", "N/A") + "\\n\\n"
    "## 基本面\\n\\n"
    + final_state.get("fundamentals_report", "N/A") + "\\n"
)

report_path = results_dir / "complete_report.md"
report_path.write_text(report_content)

print("STAGE:portfolio", flush=True)
print("ANALYSIS_COMPLETE:" + signal, flush=True)
"""


@app.post("/api/analysis/start")
async def start_analysis(request: AnalysisRequest):
    """Start a new analysis task"""
    import uuid
    task_id = f"{request.ticker}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    date = request.date or datetime.now().strftime("%Y-%m-%d")

    # Initialize task state
    app.state.task_results[task_id] = {
        "task_id": task_id,
        "ticker": request.ticker,
        "date": date,
        "status": "running",
        "progress": 0,
        "current_stage": "analysts",
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
        "error": None,
    }
    # Get API key - fail fast before storing a running task
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY environment variable not set")

    await broadcast_progress(task_id, app.state.task_results[task_id])

    # Write analysis script to temp file (avoids subprocess -c quoting issues)
    script_path = Path(f"/tmp/analysis_{task_id}.py")
    script_content = ANALYSIS_SCRIPT_TEMPLATE
    script_path.write_text(script_content)

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

    async def monitor_subprocess(task_id: str, proc: asyncio.subprocess.Process, cancel_evt: asyncio.Event):
        """Monitor subprocess stdout for stage markers and broadcast progress."""
        # Set stdout to non-blocking
        fd = proc.stdout.fileno()
        fl = fcntl.fcntl(fd, fcntl.GETFL)
        fcntl.fcntl(fd, fcntl.SETFL, fl | os.O_NONBLOCK)

        while not cancel_evt.is_set():
            if proc.returncode is not None:
                break
            await asyncio.sleep(5)
            if cancel_evt.is_set():
                break
            try:
                chunk = os.read(fd, 32768)
                if chunk:
                    for line in chunk.decode().splitlines():
                        if line.startswith("STAGE:"):
                            stage = line.split(":", 1)[1].strip()
                            _update_task_stage(stage)
                            await broadcast_progress(task_id, app.state.task_results[task_id])
            except (BlockingIOError, OSError):
                # No data available yet
                pass

    async def run_analysis():
        """Run analysis subprocess and broadcast progress"""
        try:
            # Use clean environment - don't inherit parent env
            clean_env = {k: v for k, v in os.environ.items()
                        if not k.startswith(("PYTHON", "CONDA", "VIRTUAL"))}
            clean_env["ANTHROPIC_API_KEY"] = api_key
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

            # Start monitor coroutine alongside subprocess
            monitor_task = asyncio.create_task(monitor_subprocess(task_id, proc, cancel_event))

            stdout, stderr = await proc.communicate()

            # Signal monitor to stop and wait for it
            cancel_event.set()
            try:
                await asyncio.wait_for(monitor_task, timeout=1.0)
            except asyncio.TimeoutError:
                monitor_task.cancel()

            # Clean up script file
            try:
                script_path.unlink()
            except Exception:
                pass

            if proc.returncode == 0:
                output = stdout.decode()
                decision = "HOLD"
                for line in output.splitlines():
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
                error_msg = stderr.decode()[-1000:] if stderr else "Unknown error"
                app.state.task_results[task_id]["status"] = "failed"
                app.state.task_results[task_id]["error"] = error_msg

        except Exception as e:
            cancel_event.set()
            app.state.task_results[task_id]["status"] = "failed"
            app.state.task_results[task_id]["error"] = str(e)
            try:
                script_path.unlink()
            except Exception:
                pass

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
async def get_task_status(task_id: str):
    """Get task status"""
    if task_id not in app.state.task_results:
        raise HTTPException(status_code=404, detail="Task not found")
    return app.state.task_results[task_id]


@app.get("/api/analysis/tasks")
async def list_tasks():
    """List all tasks (active and recent)"""
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
            "created_at": state.get("stages", [{}])[0].get("completed_at") if state.get("stages") else None,
        })
    # Sort by task_id (which includes timestamp) descending
    tasks.sort(key=lambda x: x["task_id"], reverse=True)
    return {"tasks": tasks, "total": len(tasks)}


@app.delete("/api/analysis/cancel/{task_id}")
async def cancel_task(task_id: str):
    """Cancel a running task"""
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
        await broadcast_progress(task_id, app.state.task_results[task_id])

    # Clean up temp script
    script_path = Path(f"/tmp/analysis_{task_id}.py")
    try:
        script_path.unlink()
    except Exception:
        pass

    return {"task_id": task_id, "status": "cancelled"}


# ============== WebSocket ==============

@app.websocket("/ws/analysis/{task_id}")
async def websocket_analysis(websocket: WebSocket, task_id: str):
    """WebSocket for real-time analysis progress"""
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
    report_dir = get_results_dir() / ticker / date
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
async def list_reports():
    return get_reports_list()


@app.get("/api/reports/{ticker}/{date}")
async def get_report(ticker: str, date: str):
    content = get_report_content(ticker, date)
    if not content:
        raise HTTPException(status_code=404, detail="Report not found")
    return content


@app.get("/")
async def root():
    return {"message": "TradingAgents Web Dashboard API", "version": "0.1.0"}


if __name__ == "__main__":
    import uvicorn
    # Run with: cd web_dashboard && ../env312/bin/python -m uvicorn main:app --reload
    # Or: cd web_dashboard/backend && python3 main.py  (requires env312 in PATH)
    uvicorn.run(app, host="0.0.0.0", port=8000)
