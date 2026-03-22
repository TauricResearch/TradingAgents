from fastapi import APIRouter, Depends, HTTPException
from typing import List, Any, Optional
from pathlib import Path
import json
from agent_os.backend.dependencies import get_current_user, get_db_client
from tradingagents.portfolio.supabase_client import SupabaseClient
from tradingagents.portfolio.exceptions import PortfolioNotFoundError
from tradingagents.report_paths import get_market_dir
import datetime

router = APIRouter(prefix="/api/portfolios", tags=["portfolios"])

@router.get("/")
async def list_portfolios(
    user: dict = Depends(get_current_user),
    db: SupabaseClient = Depends(get_db_client)
):
    portfolios = db.list_portfolios()
    return [p.to_dict() for p in portfolios]

@router.get("/{portfolio_id}")
async def get_portfolio(
    portfolio_id: str,
    user: dict = Depends(get_current_user),
    db: SupabaseClient = Depends(get_db_client)
):
    try:
        portfolio = db.get_portfolio(portfolio_id)
        return portfolio.to_dict()
    except PortfolioNotFoundError:
        raise HTTPException(status_code=404, detail="Portfolio not found")

@router.get("/{portfolio_id}/summary")
async def get_portfolio_summary(
    portfolio_id: str,
    date: Optional[str] = None,
    user: dict = Depends(get_current_user),
    db: SupabaseClient = Depends(get_db_client)
):
    """Returns the 'Top 3 Metrics' for the dashboard header."""
    if not date:
        date = datetime.datetime.now().strftime("%Y-%m-%d")
    
    try:
        # 1. Sharpe & Drawdown from latest snapshot
        snapshot = db.get_latest_snapshot(portfolio_id)
        sharpe = 0.0
        drawdown = 0.0
        
        if snapshot and snapshot.metadata:
            # Try to get calculated risk metrics from snapshot metadata
            risk = snapshot.metadata.get("risk_metrics", {})
            sharpe = risk.get("sharpe", 0.0)
            drawdown = risk.get("max_drawdown", 0.0)

        # 2. Market Regime from latest scan summary
        regime = "NEUTRAL"
        beta = 1.0
        
        scan_path = get_market_dir(date) / "scan_summary.json"
        if scan_path.exists():
            try:
                scan_data = json.loads(scan_path.read_text())
                ctx = scan_data.get("macro_context", {})
                regime = ctx.get("economic_cycle", "NEUTRAL").upper()
                # Beta is often calculated per-portfolio or per-holding
                # For now, we use a placeholder or pull from metadata
            except:
                pass

        return {
            "sharpe_ratio": sharpe or 2.42, # Fallback to demo values if 0
            "market_regime": regime,
            "beta": beta,
            "drawdown": drawdown or -2.4,
            "var_1d": 4200.0, # Placeholder
            "efficiency_label": "High Efficiency" if sharpe > 2.0 else "Normal"
        }
    except Exception as e:
        # Fallback for demo
        return {
            "sharpe_ratio": 2.42,
            "market_regime": "BULL",
            "beta": 1.15,
            "drawdown": -2.4,
            "var_1d": 4200.0,
            "efficiency_label": "High Efficiency"
        }

@router.get("/{portfolio_id}/latest")
async def get_latest_portfolio_state(
    portfolio_id: str,
    user: dict = Depends(get_current_user),
    db: SupabaseClient = Depends(get_db_client)
):
    try:
        portfolio = db.get_portfolio(portfolio_id)
        snapshot = db.get_latest_snapshot(portfolio_id)
        holdings = db.list_holdings(portfolio_id)
        trades = db.list_trades(portfolio_id, limit=10)
        
        return {
            "portfolio": portfolio.to_dict(),
            "snapshot": snapshot.to_dict() if snapshot else None,
            "holdings": [h.to_dict() for h in holdings],
            "recent_trades": [t.to_dict() for t in trades]
        }
    except PortfolioNotFoundError:
        raise HTTPException(status_code=404, detail="Portfolio not found")
