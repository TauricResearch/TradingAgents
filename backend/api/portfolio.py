from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload

from backend.core.database import get_db
from backend.models.portfolio import Portfolio, Holding
from backend.models.order import Order
from backend.models.user import User
from backend.schemas.portfolio import PortfolioRead, HoldingRead, OrderRead
from backend.api.deps import get_current_user

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("", response_model=list[PortfolioRead])
async def list_portfolios(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Portfolio).options(selectinload(Portfolio.holdings))
    )
    return result.scalars().all()


@router.get("/holdings", response_model=list[HoldingRead])
async def list_holdings(
    mode: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = select(Holding)
    if mode:
        q = q.join(Portfolio).where(Portfolio.mode == mode)
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/orders", response_model=list[OrderRead])
async def list_orders(
    mode: str | None = Query(default=None),
    ticker: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = select(Order).order_by(desc(Order.created_at)).limit(limit).offset(offset)
    if mode:
        q = q.where(Order.mode == mode)
    if ticker:
        q = q.where(Order.ticker == ticker.upper())
    result = await db.execute(q)
    return result.scalars().all()
