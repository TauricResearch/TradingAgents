from fastapi import APIRouter, HTTPException
from pathlib import Path
from typing import List, Dict, Any
import json
import sys
from datetime import datetime

# Add project root to path if not already there
project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from ..models.schemas import HistoricalAnalysisSummary, AnalysisResults
from tradingagents.default_config import DEFAULT_CONFIG

router = APIRouter(prefix="/api/history", tags=["history"])


def get_results_dir() -> Path:
    """Get the results directory path."""
    results_dir = DEFAULT_CONFIG.get("results_dir", "./results")
    return Path(results_dir)


@router.get("", response_model=List[HistoricalAnalysisSummary])
async def list_historical_analyses():
    """List all historical analyses."""
    results_dir = get_results_dir()
    if not results_dir.exists():
        return []
    
    analyses = []
    
    # Iterate through ticker directories
    for ticker_dir in results_dir.iterdir():
        if not ticker_dir.is_dir():
            continue
        
        ticker = ticker_dir.name
        
        # Iterate through date directories
        for date_dir in ticker_dir.iterdir():
            if not date_dir.is_dir():
                continue
            
            analysis_date = date_dir.name
            
            # Check if reports directory exists
            reports_dir = date_dir / "reports"
            has_results = reports_dir.exists() and any(reports_dir.glob("*.md"))
            
            analyses.append(HistoricalAnalysisSummary(
                ticker=ticker,
                analysis_date=analysis_date,
                has_results=has_results,
                completed_at=None  # Could parse from log file if needed
            ))
    
    # Sort by date (most recent first)
    analyses.sort(key=lambda x: x.analysis_date, reverse=True)
    return analyses


@router.get("/{ticker}/{date}", response_model=Dict[str, Any])
async def get_historical_analysis(ticker: str, date: str):
    """Get a specific historical analysis."""
    results_dir = get_results_dir()
    analysis_dir = results_dir / ticker / date
    
    if not analysis_dir.exists():
        raise HTTPException(status_code=404, detail="Analysis not found")
    
    reports_dir = analysis_dir / "reports"
    
    # Load reports
    reports = {}
    report_files = {
        "market_report": "market_report.md",
        "sentiment_report": "sentiment_report.md",
        "news_report": "news_report.md",
        "fundamentals_report": "fundamentals_report.md",
        "trader_investment_plan": "trader_investment_plan.md",
        "final_trade_decision": "final_trade_decision.md",
    }
    
    for key, filename in report_files.items():
        file_path = reports_dir / filename
        if file_path.exists():
            with open(file_path, "r") as f:
                reports[key] = f.read()
    
    return {
        "ticker": ticker,
        "analysis_date": date,
        "reports": reports,
        "has_results": len(reports) > 0,
    }

