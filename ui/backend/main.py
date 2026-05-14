from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
import json
from pathlib import Path
from typing import List, Dict, Any
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.agents.utils.memory import TradingMemoryLog

app = FastAPI(title="TradingAgents Dashboard API")

# Enable CORS for the React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
