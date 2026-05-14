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
from kubernetes import client, config as k8s_config
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.agents.utils.memory import TradingMemoryLog

app = FastAPI(title="TradingAgents Dashboard API")

# Initialize Kubernetes client (loads in-cluster config)
try:
    k8s_config.load_in_cluster_config()
    batch_v1 = client.BatchV1Api()
except Exception:
    batch_v1 = None

# Global state to track current active run
current_run_status = {
    "ticker": None,
    "date": None,
    "active_node": None,
    "status": "idle",
    "last_update": None
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
async def trigger_job():
    """Trigger a manual trade analysis job in Kubernetes."""
    global current_run_status
    
    # 1. Set initial status to triggered so UI knows something is happening immediately
    current_run_status.update({
        "ticker": "Portfolio",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "active_node": "Triggering Kubernetes Job...",
        "status": "triggered",
        "last_update": datetime.now().isoformat()
    })

    if not batch_v1:
        # For local development without Kubernetes, we'll simulate a bit
        current_run_status["active_node"] = "K8s Not Found (Local?)"
        raise HTTPException(status_code=500, detail="Kubernetes client not initialized (local development?)")

    namespace = "tradingagents"
    cronjob_name = "tradingagents-portfolio-daily"
    
    try:
        # 2. Get the CronJob template
        cron_job = batch_v1.read_namespaced_cron_job(cronjob_name, namespace)
        
        # 3. Define the Job object based on CronJob template
        job_name = f"manual-ui-run-{int(time.time())}"
        job = client.V1Job(
            api_version="batch/v1",
            kind="Job",
            metadata=client.V1ObjectMeta(name=job_name),
            spec=cron_job.spec.job_template.spec
        )
        
        # 4. Create the Job
        batch_v1.create_namespaced_job(namespace, job)
        
        current_run_status["active_node"] = "Job Created in K8s"
        return {"status": "triggered", "job_name": job_name}
    except Exception as e:
        current_run_status["status"] = "idle"
        current_run_status["active_node"] = f"Error: {str(e)[:50]}..."
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
