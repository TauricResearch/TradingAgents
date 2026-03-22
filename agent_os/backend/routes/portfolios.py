from fastapi import APIRouter, Depends, HTTPException
from typing import List, Any
from agent_os.backend.dependencies import get_current_user, get_db_client
from tradingagents.portfolio.supabase_client import SupabaseClient
from tradingagents.portfolio.exceptions import PortfolioNotFoundError

router = APIRouter(prefix="/api/portfolios", tags=["portfolios"])

@router.get("/")
async def list_portfolios(
    user: dict = Depends(get_current_user),
    db: SupabaseClient = Depends(get_db_client)
):
    # In V2, we would filter by user_id
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
