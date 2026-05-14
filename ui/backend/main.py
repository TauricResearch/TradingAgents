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

# Global state to track current active run
current_run_status = {
    "ticker": None,
    "date": None,
    "active_node": None,
    "status": "idle",
    "last_update": None,
    "error": k8s_init_error
}

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
async def trigger_job(data: Optional[Dict[str, str]] = None):
    """Trigger a manual trade analysis job in Kubernetes."""
    global current_run_status
    
    requested_tickers = data.get("tickers") if data else None
    display_ticker = requested_tickers if requested_tickers else "Portfolio"

    # 1. Set initial status to triggered so UI knows something is happening immediately
    current_run_status.update({
        "ticker": display_ticker,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "active_node": "Triggering Kubernetes Job...",
        "status": "triggered",
        "last_update": datetime.now().isoformat(),
        "error": k8s_init_error
    })

    if not batch_v1:
        # For local development without Kubernetes, we'll simulate a bit
        current_run_status["active_node"] = "K8s Not Found"
        current_run_status["status"] = "error"
        current_run_status["error"] = k8s_init_error or "Kubernetes client not initialized"
        raise HTTPException(status_code=500, detail=current_run_status["error"])

    namespace = "tradingagents"
    cronjob_name = "tradingagents-portfolio-daily"
    
    try:
        # 2. Get the CronJob template
        cron_job = batch_v1.read_namespaced_cron_job(cronjob_name, namespace)
        
        # 3. Define the Job object based on CronJob template
        job_name = f"manual-ui-run-{int(time.time())}"
        
        # Copy the spec and override args if specific tickers were requested
        job_spec = cron_job.spec.job_template.spec
        if requested_tickers:
            # Override the command arguments to use the specific tickers
            # Deep copy to avoid mutating the cron_job object from cache if any
            for container in job_spec.containers:
                if container.name == "trader":
                    container.args = ["portfolio", requested_tickers]

        job = k8s_client.V1Job(
            api_version="batch/v1",
            kind="Job",
            metadata=k8s_client.V1ObjectMeta(name=job_name),
            spec=job_spec
        )
        
        # 4. Create the Job
        batch_v1.create_namespaced_job(namespace, job)
        
        current_run_status["active_node"] = "Job Created in K8s"
        current_run_status["error"] = None # Clear any previous error
        return {"status": "triggered", "job_name": job_name, "tickers": requested_tickers}
    except Exception as e:
        current_run_status["status"] = "error"
        current_run_status["active_node"] = "K8s Error"
        current_run_status["error"] = str(e)
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
    global current_run_status
    current_run_status.update({
        "ticker": update.get("ticker"),
        "date": update.get("date"),
        "active_node": update.get("node"),
        "status": update.get("status"),
        "last_update": update.get("timestamp")
    })
    return {"status": "received"}

@app.get("/api/status")
async def get_current_status():
    """Return the current active run status."""
    return current_run_status

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
                        "file_path": str(log_file)
                    })
    
    # Sort by date descending
    return sorted(runs, key=lambda x: x["date"], reverse=True)

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
