from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
import json
from pathlib import Path
from typing import List, Dict, Any
from tradingagents.default_config import DEFAULT_CONFIG

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

@app.get("/api/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
