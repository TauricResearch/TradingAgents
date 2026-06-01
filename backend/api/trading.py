"""Mock trading API endpoints."""
import logging
import re
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user, get_db
from backend.services import mock_trading_service as svc

router = APIRouter(prefix="/api/trading", tags=["trading"])
_logger = logging.getLogger(__name__)

_TICKER_RE = re.compile(r'^[A-Z0-9.\-]{1,20}$')


class OrderRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=20)
    action: Literal['BUY', 'SELL']
    quantity: float = Field(..., gt=0, le=100_000)
    analysis_id: Optional[int] = None

    @field_validator('ticker')
    @classmethod
    def validate_ticker(cls, v: str) -> str:
        v = v.upper()
        if not _TICKER_RE.match(v):
            raise ValueError('Ticker must be 1–20 alphanumeric characters')
        return v


class ResetRequest(BaseModel):
    initial_capital: float = Field(default=100_000.0, gt=0, le=10_000_000)


@router.get("/portfolio")
async def get_portfolio(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Simulation portfolio with live prices and P&L."""
    try:
        return await svc.get_portfolio_with_live_prices(db)
    except Exception as exc:
        _logger.error("get_portfolio failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


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
            ticker=req.ticker,
            action=req.action,
            quantity=req.quantity,
            analysis_id=req.analysis_id,
        )
        await db.commit()
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        _logger.error("create_order failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/performance")
async def get_performance(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Portfolio performance metrics vs SPY benchmark."""
    try:
        return await svc.get_performance(db)
    except Exception as exc:
        _logger.error("get_performance failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


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
        _logger.error("reset_portfolio failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
