"""FastAPI server for Nifty50 AI recommendations."""
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import database as db
import sys
import os
from pathlib import Path
from datetime import datetime
import threading

# Add parent directories to path for importing trading agents
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Track running analyses
running_analyses = {}  # {symbol: {"status": "running", "started_at": datetime, "progress": str}}

app = FastAPI(
    title="Nifty50 AI API",
    description="API for Nifty 50 stock recommendations",
    version="1.0.0"
)

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class StockAnalysis(BaseModel):
    symbol: str
    company_name: str
    decision: Optional[str] = None
    confidence: Optional[str] = None
    risk: Optional[str] = None
    raw_analysis: Optional[str] = None


class TopPick(BaseModel):
    rank: int
    symbol: str
    company_name: str
    decision: str
    reason: str
    risk_level: str


class StockToAvoid(BaseModel):
    symbol: str
    company_name: str
    reason: str


class Summary(BaseModel):
    total: int
    buy: int
    sell: int
    hold: int


class DailyRecommendation(BaseModel):
    date: str
    analysis: dict[str, StockAnalysis]
    summary: Summary
    top_picks: list[TopPick]
    stocks_to_avoid: list[StockToAvoid]


class SaveRecommendationRequest(BaseModel):
    date: str
    analysis: dict
    summary: dict
    top_picks: list
    stocks_to_avoid: list


# ============== Pipeline Data Models ==============

class AgentReport(BaseModel):
    agent_type: str
    report_content: str
    data_sources_used: Optional[list] = []
    created_at: Optional[str] = None


class DebateHistory(BaseModel):
    debate_type: str
    bull_arguments: Optional[str] = None
    bear_arguments: Optional[str] = None
    risky_arguments: Optional[str] = None
    safe_arguments: Optional[str] = None
    neutral_arguments: Optional[str] = None
    judge_decision: Optional[str] = None
    full_history: Optional[str] = None


class PipelineStep(BaseModel):
    step_number: int
    step_name: str
    status: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_ms: Optional[int] = None
    output_summary: Optional[str] = None


class DataSourceLog(BaseModel):
    source_type: str
    source_name: str
    data_fetched: Optional[dict] = None
    fetch_timestamp: Optional[str] = None
    success: bool = True
    error_message: Optional[str] = None


class SavePipelineDataRequest(BaseModel):
    date: str
    symbol: str
    agent_reports: Optional[dict] = None
    investment_debate: Optional[dict] = None
    risk_debate: Optional[dict] = None
    pipeline_steps: Optional[list] = None
    data_sources: Optional[list] = None


class RunAnalysisRequest(BaseModel):
    symbol: str
    date: Optional[str] = None  # Defaults to today if not provided


def run_analysis_task(symbol: str, date: str):
    """Background task to run trading analysis for a stock."""
    global running_analyses

    try:
        running_analyses[symbol] = {
            "status": "initializing",
            "started_at": datetime.now().isoformat(),
            "progress": "Loading trading agents..."
        }

        # Import trading agents
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        from tradingagents.default_config import DEFAULT_CONFIG

        running_analyses[symbol]["progress"] = "Initializing analysis pipeline..."

        # Create config
        config = DEFAULT_CONFIG.copy()
        config["llm_provider"] = "anthropic"  # Use Claude for all LLM
        config["deep_think_llm"] = "opus"  # Claude Opus (Claude Max CLI alias)
        config["quick_think_llm"] = "sonnet"  # Claude Sonnet (Claude Max CLI alias)
        config["max_debate_rounds"] = 1

        running_analyses[symbol]["status"] = "running"
        running_analyses[symbol]["progress"] = "Running market analysis..."

        # Initialize and run
        ta = TradingAgentsGraph(debug=False, config=config)

        running_analyses[symbol]["progress"] = f"Analyzing {symbol}..."
        final_state, decision = ta.propagate(symbol, date)

        running_analyses[symbol] = {
            "status": "completed",
            "completed_at": datetime.now().isoformat(),
            "progress": f"Analysis complete: {decision}",
            "decision": decision
        }

    except Exception as e:
        error_msg = str(e) if str(e) else f"{type(e).__name__}: No details provided"
        running_analyses[symbol] = {
            "status": "error",
            "error": error_msg,
            "progress": f"Error: {error_msg[:100]}"
        }
        import traceback
        print(f"Analysis error for {symbol}: {type(e).__name__}: {error_msg}")
        traceback.print_exc()


@app.get("/")
async def root():
    """API root endpoint."""
    return {
        "name": "Nifty50 AI API",
        "version": "2.0.0",
        "endpoints": {
            "GET /recommendations": "Get all recommendations",
            "GET /recommendations/latest": "Get latest recommendation",
            "GET /recommendations/{date}": "Get recommendation by date",
            "GET /recommendations/{date}/{symbol}/pipeline": "Get full pipeline data for a stock",
            "GET /recommendations/{date}/{symbol}/agents": "Get agent reports for a stock",
            "GET /recommendations/{date}/{symbol}/debates": "Get debate history for a stock",
            "GET /recommendations/{date}/{symbol}/data-sources": "Get data source logs for a stock",
            "GET /recommendations/{date}/pipeline-summary": "Get pipeline summary for all stocks on a date",
            "GET /stocks/{symbol}/history": "Get stock history",
            "GET /dates": "Get all available dates",
            "POST /recommendations": "Save a new recommendation",
            "POST /pipeline": "Save pipeline data for a stock"
        }
    }


@app.get("/recommendations")
async def get_all_recommendations():
    """Get all daily recommendations."""
    recommendations = db.get_all_recommendations()
    return {"recommendations": recommendations, "count": len(recommendations)}


@app.get("/recommendations/latest")
async def get_latest_recommendation():
    """Get the most recent recommendation."""
    recommendation = db.get_latest_recommendation()
    if not recommendation:
        raise HTTPException(status_code=404, detail="No recommendations found")
    return recommendation


@app.get("/recommendations/{date}")
async def get_recommendation_by_date(date: str):
    """Get recommendation for a specific date (format: YYYY-MM-DD)."""
    recommendation = db.get_recommendation_by_date(date)
    if not recommendation:
        raise HTTPException(status_code=404, detail=f"No recommendation found for {date}")
    return recommendation


@app.get("/stocks/{symbol}/history")
async def get_stock_history(symbol: str):
    """Get historical recommendations for a specific stock."""
    history = db.get_stock_history(symbol.upper())
    return {"symbol": symbol.upper(), "history": history, "count": len(history)}


@app.get("/dates")
async def get_available_dates():
    """Get all dates with recommendations."""
    dates = db.get_all_dates()
    return {"dates": dates, "count": len(dates)}


@app.post("/recommendations")
async def save_recommendation(request: SaveRecommendationRequest):
    """Save a new daily recommendation."""
    try:
        db.save_recommendation(
            date=request.date,
            analysis_data=request.analysis,
            summary=request.summary,
            top_picks=request.top_picks,
            stocks_to_avoid=request.stocks_to_avoid
        )
        return {"message": f"Recommendation for {request.date} saved successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "database": "connected"}


# ============== Pipeline Data Endpoints ==============

@app.get("/recommendations/{date}/{symbol}/pipeline")
async def get_pipeline_data(date: str, symbol: str):
    """Get full pipeline data for a stock on a specific date."""
    pipeline_data = db.get_full_pipeline_data(date, symbol.upper())

    # Check if we have any data
    has_data = (
        pipeline_data.get('agent_reports') or
        pipeline_data.get('debates') or
        pipeline_data.get('pipeline_steps') or
        pipeline_data.get('data_sources')
    )

    if not has_data:
        # Return empty structure with mock pipeline steps if no data
        return {
            "date": date,
            "symbol": symbol.upper(),
            "agent_reports": {},
            "debates": {},
            "pipeline_steps": [],
            "data_sources": [],
            "status": "no_data"
        }

    return {**pipeline_data, "status": "complete"}


@app.get("/recommendations/{date}/{symbol}/agents")
async def get_agent_reports(date: str, symbol: str):
    """Get agent reports for a stock on a specific date."""
    reports = db.get_agent_reports(date, symbol.upper())
    return {
        "date": date,
        "symbol": symbol.upper(),
        "reports": reports,
        "count": len(reports)
    }


@app.get("/recommendations/{date}/{symbol}/debates")
async def get_debate_history(date: str, symbol: str):
    """Get debate history for a stock on a specific date."""
    debates = db.get_debate_history(date, symbol.upper())
    return {
        "date": date,
        "symbol": symbol.upper(),
        "debates": debates
    }


@app.get("/recommendations/{date}/{symbol}/data-sources")
async def get_data_sources(date: str, symbol: str):
    """Get data source logs for a stock on a specific date."""
    logs = db.get_data_source_logs(date, symbol.upper())
    return {
        "date": date,
        "symbol": symbol.upper(),
        "data_sources": logs,
        "count": len(logs)
    }


@app.get("/recommendations/{date}/pipeline-summary")
async def get_pipeline_summary(date: str):
    """Get pipeline summary for all stocks on a specific date."""
    summary = db.get_pipeline_summary_for_date(date)
    return {
        "date": date,
        "stocks": summary,
        "count": len(summary)
    }


@app.post("/pipeline")
async def save_pipeline_data(request: SavePipelineDataRequest):
    """Save pipeline data for a stock."""
    try:
        db.save_full_pipeline_data(
            date=request.date,
            symbol=request.symbol.upper(),
            pipeline_data={
                'agent_reports': request.agent_reports,
                'investment_debate': request.investment_debate,
                'risk_debate': request.risk_debate,
                'pipeline_steps': request.pipeline_steps,
                'data_sources': request.data_sources
            }
        )
        return {"message": f"Pipeline data for {request.symbol} on {request.date} saved successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============== Analysis Endpoints ==============

@app.post("/analyze/{symbol}")
async def run_analysis(symbol: str, background_tasks: BackgroundTasks, date: Optional[str] = None):
    """Trigger analysis for a stock. Runs in background."""
    symbol = symbol.upper()

    # Check if analysis is already running
    if symbol in running_analyses and running_analyses[symbol].get("status") == "running":
        return {
            "message": f"Analysis already running for {symbol}",
            "status": running_analyses[symbol]
        }

    # Use today's date if not provided
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    # Start analysis in background thread
    thread = threading.Thread(target=run_analysis_task, args=(symbol, date))
    thread.start()

    return {
        "message": f"Analysis started for {symbol}",
        "symbol": symbol,
        "date": date,
        "status": "started"
    }


@app.get("/analyze/{symbol}/status")
async def get_analysis_status(symbol: str):
    """Get the status of a running or completed analysis."""
    symbol = symbol.upper()

    if symbol not in running_analyses:
        return {
            "symbol": symbol,
            "status": "not_started",
            "message": "No analysis has been run for this stock"
        }

    return {
        "symbol": symbol,
        **running_analyses[symbol]
    }


@app.get("/analyze/running")
async def get_running_analyses():
    """Get all currently running analyses."""
    running = {k: v for k, v in running_analyses.items() if v.get("status") == "running"}
    return {
        "running": running,
        "count": len(running)
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
