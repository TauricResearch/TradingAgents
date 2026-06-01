"""Mock trading API endpoints."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user, get_db
from backend.services import mock_trading_service as svc

router = APIRouter(prefix="/api/trading", tags=["trading"])


class OrderRequest(BaseModel):
    ticker: str
    action: str       # BUY | SELL
    quantity: float
    analysis_id: Optional[int] = None


class ResetRequest(BaseModel):
    initial_capital: float = 100_000.0


@router.get("/portfolio")
async def get_portfolio(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Simulation portfolio with live prices and P&L."""
    try:
        return await svc.get_portfolio_with_live_prices(db)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/order", status_code=status.HTTP_201_CREATED)
async def create_order(
    req: OrderRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Execute a paper BUY or SELL order."""
    try:
        result = await svc.execute_order(
            db,
            ticker=req.ticker.upper(),
            action=req.action,
            quantity=req.quantity,
            analysis_id=req.analysis_id,
        )
        await db.commit()
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/performance")
async def get_performance(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Portfolio performance metrics vs SPY benchmark."""
    try:
        return await svc.get_performance(db)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/reset")
async def reset_portfolio(
    req: ResetRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Reset simulation portfolio to initial capital."""
    try:
        result = await svc.reset_portfolio(db, initial_capital=req.initial_capital)
        await db.commit()
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
