from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
import json
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from threading import Lock
from uuid import uuid4

import sys

# Standard Kubernetes import
k8s_import_error_msg = None
try:
    import kubernetes
    from kubernetes import client as k8s_client
    import kubernetes.config as k8s_config
    
    # Exhaustive diagnostic logging
    print(f"DEBUG: Kubernetes library file: {getattr(kubernetes, '__file__', 'unknown')}")
    print(f"DEBUG: k8s_config module: {k8s_config}")
    print(f"DEBUG: k8s_config file: {getattr(k8s_config, '__file__', 'unknown')}")
    print(f"DEBUG: k8s_config dir: {dir(k8s_config)}")
    
    # Newer kubernetes clients expose load_incluster_config (no extra underscore).
    # Keep a fallback to the legacy/misspelled lookup so startup is resilient across versions.
    load_fn = getattr(k8s_config, 'load_incluster_config', None)
    if not load_fn:
        # Check submodules explicitly
        import kubernetes.config.incluster_config as inc
        print(f"DEBUG: incluster_config dir: {dir(inc)}")
        load_fn = getattr(inc, 'load_incluster_config', None)
    if not load_fn:
        load_fn = getattr(k8s_config, 'load_in_cluster_config', None)
    
    if load_fn:
        load_in_cluster_config = load_fn
        print("DEBUG: Successfully located in-cluster config loader")
    else:
        raise ImportError("Could not locate load_incluster_config in kubernetes.config or its submodules")

    # Repeat for kube_config
    load_kube_fn = getattr(k8s_config, 'load_kube_config', None)
    if not load_kube_fn:
        import kubernetes.config.kube_config as kc
        load_kube_fn = getattr(kc, 'load_kube_config', None)
    
    if load_kube_fn:
        load_kube_config = load_kube_fn
    else:
        raise ImportError("Could not locate load_kube_config")

except Exception as e:
    k8s_import_error_msg = f"K8s Import Failed: {str(e)}"
    print(f"DEBUG: {k8s_import_error_msg}")
    kubernetes = None
    k8s_client = None
    load_in_cluster_config = None
    load_kube_config = None

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.utils.memory import TradingMemoryLog

app = FastAPI(title="TradingAgents Dashboard API")

# Initialize Kubernetes client
batch_v1 = None
k8s_init_error = k8s_import_error_msg

if kubernetes and k8s_client and load_in_cluster_config:
    try:
        print("Attempting to load in-cluster Kubernetes config...")
        load_in_cluster_config()
        batch_v1 = k8s_client.BatchV1Api()
        print("Successfully loaded in-cluster Kubernetes config.")
    except Exception as e:
        k8s_init_error = f"In-cluster failed: {str(e)}"
        print(k8s_init_error)
        try:
            print("Attempting to load local kube-config...")
            load_kube_config()
            batch_v1 = k8s_client.BatchV1Api()
            print("Successfully loaded local kube-config.")
            k8s_init_error = None # Success
        except Exception as e2:
            k8s_init_error = f"{k8s_init_error} | Local failed: {str(e2)}"
            print(k8s_init_error)
            print("Kubernetes client will not be available.")
else:
    if not k8s_init_error:
        k8s_init_error = f"Kubernetes library error: lib={bool(kubernetes)} client={bool(k8s_client)} loader={bool(load_in_cluster_config)}"
    print(k8s_init_error)

def _make_idle_status() -> Dict[str, Any]:
    return {
        "run_id": None,
        "ticker": None,
        "date": None,
        "active_node": None,
        "completed_nodes": [],
        "updates": {},
        "status": "idle",
        "last_update": None,
        "start_time": None,
        "end_time": None,
        "error": k8s_init_error,
        "requested_tickers": [],
        "tickers": {},
    }


def _parse_ticker_list(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    return [ticker.strip().upper() for ticker in raw.split(",") if ticker.strip()]


def _make_run_status(run_id: str, display_ticker: str, requested_tickers: List[str]) -> Dict[str, Any]:
    start_time = datetime.utcnow().isoformat() + "Z"
    return {
        "run_id": run_id,
        "ticker": display_ticker,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "active_node": "Initializing...",
        "completed_nodes": [],
        "updates": {},
        "status": "triggered",
        "last_update": start_time,
        "start_time": start_time,
        "end_time": None,
        "error": k8s_init_error,
        "requested_tickers": requested_tickers,
        "tickers": {},
    }


run_statuses: Dict[str, Dict[str, Any]] = {}
run_status_lock = Lock()
latest_run_id: Optional[str] = None


def _get_latest_run_status() -> Dict[str, Any]:
    with run_status_lock:
        if latest_run_id and latest_run_id in run_statuses:
            return run_statuses[latest_run_id]
        if run_statuses:
            newest = max(
                run_statuses.values(),
                key=lambda status: status.get("start_time") or "",
            )
            return newest
    return _make_idle_status()


def _recompute_run_summary(run_status: Dict[str, Any]) -> None:
    ticker_states = run_status.get("tickers", {})
    if not ticker_states:
        return

    statuses = [state.get("status") for state in ticker_states.values()]
    if any(status in {"triggered", "in_progress"} for status in statuses):
        run_status["status"] = "in_progress"
        return
    if statuses and all(status == "error" for status in statuses):
        run_status["status"] = "error"
        return
    if any(status == "completed" for status in statuses):
        run_status["status"] = "completed"

# Enable CORS for the React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PORTFOLIO_PATH = Path(DEFAULT_CONFIG.get("results_dir", "results")).parent / "portfolio.txt"

@app.get("/api/config/portfolio")
async def get_portfolio_config():
    """Read the current ticker list from portfolio.txt."""
    if not PORTFOLIO_PATH.exists():
        return {"tickers": "NVDA,AAPL,MSFT,TSLA,GOOGL"} # Default
    return {"tickers": PORTFOLIO_PATH.read_text().strip()}

@app.post("/api/jobs/trigger")
async def trigger_job(data: Optional[Dict[str, Any]] = None):
    """Trigger a manual trade analysis job in Kubernetes."""
    global latest_run_id
    
    requested_tickers = data.get("tickers") if data else None
    requested_analysts = data.get("analysts") if data else None
    is_standalone = data.get("standalone", False) if data else False
    requested_ticker_list = _parse_ticker_list(requested_tickers)
    run_id = str(uuid4())
    
    # Use requested tickers or fall back to the saved portfolio file for display
    display_ticker = requested_tickers
    if not display_ticker:
        if PORTFOLIO_PATH.exists():
            display_ticker = PORTFOLIO_PATH.read_text().strip()
        else:
            display_ticker = "Portfolio"

    with run_status_lock:
        run_statuses[run_id] = _make_run_status(run_id, display_ticker, requested_ticker_list)
        latest_run_id = run_id

    if not batch_v1:
        # For local development without Kubernetes, we'll simulate a bit
        with run_status_lock:
            run_statuses[run_id]["active_node"] = "K8s Not Found"
            run_statuses[run_id]["status"] = "error"
            run_statuses[run_id]["error"] = k8s_init_error or "Kubernetes client not initialized"
        raise HTTPException(status_code=500, detail=run_statuses[run_id]["error"])

    namespace = "tradingagents"
    cronjob_name = "tradingagents-portfolio-daily"
    
    try:
        # 2. Get the CronJob template
        cron_job = batch_v1.read_namespaced_cron_job(cronjob_name, namespace)
        
        # 3. Define the Job object based on CronJob template
        job_name = f"manual-ui-run-{int(time.time())}"
        
        # Copy the spec and override args if specific tickers were requested
        job_spec = cron_job.spec.job_template.spec
        
        # Build arguments for the trader command
        cmd_args = ["portfolio"]
        if requested_tickers:
            cmd_args.append(requested_tickers)
        else:
            # If no tickers, portfolio command still needs an argument or empty string
            # to trigger reading from portfolio.txt if it's the first positional arg
            # But the CLI portfolio command takes Argument(None), so we can skip it.
            pass
            
        if requested_analysts:
            cmd_args.extend(["--analysts", requested_analysts])
        if is_standalone:
            cmd_args.append("--standalone")
        cmd_args.extend(["--run-id", run_id])

        # Override the command arguments
        for container in job_spec.template.spec.containers:
            if container.name == "trader":
                container.args = cmd_args

        job = k8s_client.V1Job(
            api_version="batch/v1",
            kind="Job",
            metadata=k8s_client.V1ObjectMeta(name=job_name),
            spec=job_spec
        )
        
        # 4. Create the Job
        batch_v1.create_namespaced_job(namespace, job)
        
        with run_status_lock:
            run_statuses[run_id]["active_node"] = "Job Created in K8s"
            run_statuses[run_id]["error"] = None
        return {
            "status": "triggered",
            "job_name": job_name,
            "tickers": requested_tickers,
            "run_id": run_id,
        }
    except Exception as e:
        with run_status_lock:
            run_statuses[run_id]["status"] = "error"
            run_statuses[run_id]["active_node"] = "K8s Error"
            run_statuses[run_id]["error"] = str(e)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/config/portfolio")
async def update_portfolio_config(data: Dict[str, str]):
    """Update the ticker list in portfolio.txt."""
    tickers = data.get("tickers", "").strip()
    if not tickers:
        raise HTTPException(status_code=400, detail="Tickers cannot be empty")
    
    PORTFOLIO_PATH.write_text(tickers)
    return {"status": "updated", "tickers": tickers}

@app.post("/api/webhook/progress")
async def handle_progress_webhook(update: Dict[str, Any]):
    """Receive progress updates from the TradingAgentsGraph."""
    global latest_run_id

    run_id = update.get("run_id") or "legacy"
    ticker = update.get("ticker") or "UNKNOWN"
    node = update.get("node")

    with run_status_lock:
        if run_id not in run_statuses:
            run_statuses[run_id] = _make_run_status(run_id, ticker, [])
        latest_run_id = run_id
        run_status = run_statuses[run_id]

        ticker_state = run_status["tickers"].setdefault(
            ticker,
            {
                "ticker": ticker,
                "date": update.get("date"),
                "active_node": None,
                "completed_nodes": [],
                "updates": {},
                "status": "triggered",
                "last_update": None,
                "start_time": update.get("start_time"),
                "end_time": None,
                "error": None,
            },
        )

        if node:
            if node not in ticker_state["completed_nodes"]:
                ticker_state["completed_nodes"].append(node)
            ticker_state["active_node"] = node

        if "updates" in update:
            ticker_state["updates"].update(update["updates"])

        ticker_state.update({
            "date": update.get("date"),
            "status": update.get("status") or ticker_state.get("status"),
            "last_update": update.get("timestamp"),
            "start_time": update.get("start_time") or ticker_state.get("start_time"),
            "end_time": update.get("end_time") or ticker_state.get("end_time"),
            "error": update.get("error"),
        })

        run_status.update({
            "ticker": ticker,
            "date": update.get("date"),
            "active_node": ticker_state.get("active_node"),
            "completed_nodes": list(ticker_state.get("completed_nodes", [])),
            "updates": dict(ticker_state.get("updates", {})),
            "last_update": update.get("timestamp"),
            "start_time": run_status.get("start_time") or update.get("start_time"),
            "end_time": update.get("end_time") or run_status.get("end_time"),
            "error": update.get("error"),
        })
        _recompute_run_summary(run_status)
    return {"status": "received"}

@app.get("/api/status")
async def get_current_status():
    """Return the current active run status."""
    return _get_latest_run_status()

@app.get("/api/status/{run_id}")
async def get_run_status(run_id: str):
    """Return the status for a specific run."""
    with run_status_lock:
        if run_id not in run_statuses:
            raise HTTPException(status_code=404, detail="Run status not found")
        return run_statuses[run_id]

@app.get("/api/statuses")
async def list_run_statuses():
    """List known run statuses ordered by newest first."""
    with run_status_lock:
        statuses = sorted(
            run_statuses.values(),
            key=lambda status: status.get("start_time") or "",
            reverse=True,
        )
    return statuses

RESULTS_DIR = Path(DEFAULT_CONFIG.get("results_dir", "results"))

MEMORY_LOG_PATH = Path(DEFAULT_CONFIG.get("memory_log_path", os.path.expanduser("~/.tradingagents/memory/trading_memory.md")))

@app.get("/api/runs")
async def list_runs() -> List[Dict[str, Any]]:
    """List all available trade runs organized by ticker."""
    runs = []
    if not RESULTS_DIR.exists():
        return []
    
    for ticker_dir in RESULTS_DIR.iterdir():
        if ticker_dir.is_dir():
            logs_dir = ticker_dir / "TradingAgentsStrategy_logs"
            if logs_dir.exists():
                for log_file in logs_dir.glob("full_states_log_*.json"):
                    # Extract date from filename: full_states_log_YYYY-MM-DD.json
                    date_str = log_file.stem.replace("full_states_log_", "")
                    runs.append({
                        "ticker": ticker_dir.name,
                        "date": date_str,
                        "file_path": str(log_file),
                        "mtime": log_file.stat().st_mtime
                    })
    
    # Sort by mtime descending (newest file first)
    return sorted(runs, key=lambda x: x["mtime"], reverse=True)

@app.get("/api/runs/{ticker}/{date}")
async def get_run_detail(ticker: str, date: str):
    """Retrieve the full state log for a specific ticker and date."""
    log_path = RESULTS_DIR / ticker / "TradingAgentsStrategy_logs" / f"full_states_log_{date}.json"
    
    if not log_path.exists():
        raise HTTPException(status_code=404, detail="Run log not found")
        
    with open(log_path, "r", encoding="utf-8") as f:
        return json.load(f)

@app.get("/api/stats")
async def get_stats() -> Dict[str, Any]:
    """Aggregate performance metrics from memory logs."""
    memory_log = TradingMemoryLog(config={"memory_log_path": str(MEMORY_LOG_PATH)})
    entries = memory_log.load_entries()
    
    resolved = [e for e in entries if not e.get("pending")]
    
    total_trades = len(resolved)
    wins = 0
    for e in resolved:
        try:
            # Alpha is formatted like "+1.5%" or "-2.0%"
            alpha_val = float(e["alpha"].replace('%', ''))
            if alpha_val > 0:
                wins += 1
        except (ValueError, TypeError, KeyError):
            pass
            
    return {
        "total_trades": total_trades,
        "win_rate": (wins / total_trades * 100) if total_trades > 0 else 0,
        "history": resolved
    }

@app.get("/api/reflections")
async def get_reflections() -> List[Dict[str, Any]]:
    """Retrieve all logged reflections."""
    memory_log = TradingMemoryLog(config={"memory_log_path": str(MEMORY_LOG_PATH)})
    entries = memory_log.load_entries()
    return [e for e in entries if e.get("reflection")]

@app.get("/api/health")
async def health_check():
    return {"status": "healthy"}

# Serve React Static Files
frontend_path = Path("frontend_build")
if frontend_path.exists():
    app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="ui")
    
    @app.get("/{full_path:path}")
    async def serve_react(full_path: str):
        if full_path.startswith("api"):
            raise HTTPException(status_code=404)
        return FileResponse(frontend_path / "index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
