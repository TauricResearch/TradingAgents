from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, Optional
import json
import os
from datetime import datetime
import glob
import uuid

# Import your TradingAgents components
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), "../.."))
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

app = FastAPI(title="TradingAgents API", version="1.0.0", debug=True)

# Centralized results directory to avoid repetition
RESULTS_BASE = os.path.join(os.path.dirname(__file__), "..", "..", "output_data")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models
class AnalysisRequest(BaseModel):
    symbol: str
    date: str
    config_overrides: Optional[Dict[str, Any]] = None

class AnalysisResponse(BaseModel):
    job_id: str
    status: str
    message: str

class JobStatus(BaseModel):
    job_id: str
    status: str
    progress: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

# In-memory job storage (in production, use Redis or database)
jobs: Dict[str, JobStatus] = {}

@app.get("/")
async def root():
    return {"message": "TradingAgents API is running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

async def run_analysis_task(job_id: str, symbol: str, analysis_date: str, config_overrides: Dict[str, Any] = None):
    """Background task to run the trading analysis"""
    try:
        jobs[job_id].status = "running"
        jobs[job_id].progress = "Initializing TradingAgents..."
        
        # Create custom config
        config = DEFAULT_CONFIG.copy()
        if config_overrides:
            config.update(config_overrides)
        
        # Initialize TradingAgents
        jobs[job_id].progress = "Setting up trading graph..."

        # Do not set API keys in code. Use environment variables or a secure secret manager.
        ta = TradingAgentsGraph(debug=True, config=config)
        
        # Run the analysis
        jobs[job_id].progress = f"Analyzing {symbol} for {analysis_date}..."
        _, decision = ta.propagate(symbol, analysis_date)
        
        print(_)
        print("Decision: ", decision)
        
        jobs[job_id].status = "completed"
        jobs[job_id].result = {
            "symbol": symbol,
            "date": analysis_date,
            "decision": decision,
            "completed_at": datetime.now().isoformat()
        }
        jobs[job_id].progress = "Analysis completed successfully"
        
    except Exception as e:
        jobs[job_id].status = "failed"
        jobs[job_id].error = str(e)
        jobs[job_id].progress = f"Error: {str(e)}"

@app.post("/analysis/start", response_model=AnalysisResponse)
async def start_analysis(request: AnalysisRequest, background_tasks: BackgroundTasks):
    """Start a new trading analysis"""
    job_id = str(uuid.uuid4())

    # Normalize inputs
    symbol = request.symbol.upper().strip()
    date = request.date.strip()

    # Validate date format
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    # Initialize job
    jobs[job_id] = JobStatus(
        job_id=job_id,
        status="queued",
        progress="Analysis queued"
    )

    # Start background task
    background_tasks.add_task(
        run_analysis_task, 
        job_id, 
        symbol,
        date,
        request.config_overrides or {}
    )

    return AnalysisResponse(
        job_id=job_id,
        status="queued",
        message=f"Analysis started for {symbol} on {date}"
    )

@app.get("/analysis/status/{job_id}", response_model=JobStatus)
async def get_analysis_status(job_id: str):
    """Get the status of a running analysis"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return jobs[job_id]

@app.get("/results/companies")
async def get_companies():
    """Get list of companies with analysis results"""
    results_dir = RESULTS_BASE
    if not os.path.exists(results_dir):
        return {"companies": []}
    
    companies = []
    for company_dir in os.listdir(results_dir):
        company_path = os.path.join(results_dir, company_dir)
        if os.path.isdir(company_path):
            # Check both regular logs and transformed logs
            logs_dir = os.path.join(company_path, "TradingAgentsStrategy_logs")
            transformed_logs_dir = os.path.join(company_path, "TradingAgentsStrategy_transformed_logs")
            
            total_analyses = 0
            latest_date = None
            
            # Count regular analyses
            if os.path.exists(logs_dir):
                json_files = glob.glob(os.path.join(logs_dir, "*.json"))
                total_analyses += len(json_files)
                if json_files:
                    latest_file = max(json_files, key=os.path.getctime)
                    latest_date = os.path.basename(latest_file).replace("full_states_log_", "").replace(".json", "")
            
            # Count transformed analyses
            transformed_count = 0
            if os.path.exists(transformed_logs_dir):
                transformed_files = glob.glob(os.path.join(transformed_logs_dir, "*_transformed.json"))
                transformed_count = len(transformed_files)
            
            if total_analyses > 0 or transformed_count > 0:
                companies.append({
                    "symbol": company_dir,
                    "latest_analysis": latest_date,
                    "total_analyses": total_analyses,
                    "transformed_analyses": transformed_count
                })
    
    return {"companies": companies}

@app.get("/results/{symbol}")
async def get_company_results(symbol: str):
    """Get all analysis results for a specific company"""
    results_dir = os.path.join(RESULTS_BASE, symbol.upper(), "TradingAgentsStrategy_logs")
    
    if not os.path.exists(results_dir):
        raise HTTPException(status_code=404, detail=f"No results found for {symbol}")
    
    results = []
    json_files = glob.glob(os.path.join(results_dir, "*.json"))
    
    for file_path in sorted(json_files, key=os.path.getctime, reverse=True):
        filename = os.path.basename(file_path)
        analysis_date = filename.replace("full_states_log_", "").replace(".json", "")
        
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
                
            results.append({
                "date": analysis_date,
                "filename": filename,
                "file_size": os.path.getsize(file_path),
                "modified_at": datetime.fromtimestamp(os.path.getmtime(file_path)).isoformat(),
                "preview": {
                    "keys": list(data.keys()) if isinstance(data, dict) else "Not a dict",
                    "size": len(str(data))
                }
            })
        except Exception as e:
            results.append({
                "date": analysis_date,
                "filename": filename,
                "error": f"Could not read file: {str(e)}"
            })
    
    return {"symbol": symbol.upper(), "results": results}

@app.get("/transformed-results/{symbol}")
async def get_transformed_company_results(symbol: str):
    """Get all transformed analysis results for a specific company"""
    results_dir = os.path.join(RESULTS_BASE, symbol.upper(), "TradingAgentsStrategy_transformed_logs")
    
    if not os.path.exists(results_dir):
        raise HTTPException(status_code=404, detail=f"No transformed results found for {symbol}")
    
    results = []
    json_files = glob.glob(os.path.join(results_dir, "*_transformed.json"))
    
    for file_path in sorted(json_files, key=os.path.getctime, reverse=True):
        filename = os.path.basename(file_path)
        # Extract date from filename like "full_states_log_2025-07-26_transformed.json"
        analysis_date = filename.replace("full_states_log_", "").replace("_transformed.json", "")
        
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
                
            results.append({
                "date": analysis_date,
                "filename": filename,
                "file_size": os.path.getsize(file_path),
                "modified_at": datetime.fromtimestamp(os.path.getmtime(file_path)).isoformat(),
                "preview": {
                    "company_ticker": data.get("metadata", {}).get("company_ticker", "N/A"),
                    "final_recommendation": data.get("metadata", {}).get("final_recommendation", "N/A"),
                    "confidence_level": data.get("metadata", {}).get("confidence_level", "N/A"),
                    "current_price": data.get("financial_data", {}).get("current_price", 0)
                }
            })
        except Exception as e:
            results.append({
                "date": analysis_date,
                "filename": filename,
                "error": f"Could not read file: {str(e)}"
            })
    
    return {"symbol": symbol.upper(), "results": results}

@app.get("/results/{symbol}/{date}")
async def get_specific_result(symbol: str, date: str):
    """Get specific analysis result"""
    file_path = os.path.join(
        RESULTS_BASE,
        symbol.upper(),
        "TradingAgentsStrategy_logs",
        f"full_states_log_{date}.json",
    )
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"No result found for {symbol} on {date}")
    
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        return {
            "symbol": symbol.upper(),
            "date": date,
            "data": data,
            "metadata": {
                "file_size": os.path.getsize(file_path),
                "modified_at": datetime.fromtimestamp(os.path.getmtime(file_path)).isoformat()
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading result: {str(e)}")

@app.get("/transformed-results/{symbol}/{date}")
async def get_specific_transformed_result(symbol: str, date: str):
    """Get specific transformed analysis result"""
    file_path = os.path.join(
        RESULTS_BASE,
        symbol.upper(),
        "TradingAgentsStrategy_transformed_logs",
        f"full_states_log_{date}_transformed.json",
    )
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"Transformed result not found for {symbol} on {date}")
    
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        return {
            "symbol": symbol.upper(),
            "date": date,
            "data": data,
            "file_info": {
                "filename": os.path.basename(file_path),
                "file_size": os.path.getsize(file_path),
                "modified_at": datetime.fromtimestamp(os.path.getmtime(file_path)).isoformat()
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")

@app.get("/config")
async def get_default_config():
    """Get the default configuration"""
    return {"config": DEFAULT_CONFIG}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
