"""Portfolio: positions CRUD + summary with live-price valuation."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from gui import storage
from service.streaming import broadcaster

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


class Position(BaseModel):
    id: int
    ticker: str
    shares: float
    cost_basis_per_share: float
    opened_at: str
    closed_at: Optional[str] = None
    closing_price: Optional[float] = None
    account: Optional[str] = None
    notes: Optional[str] = None


class PositionCreateRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=32)
    shares: float = Field(gt=0)
    cost_basis_per_share: float = Field(gt=0)
    opened_at: Optional[str] = None
    account: Optional[str] = None
    notes: Optional[str] = None


class PositionUpdateRequest(BaseModel):
    shares: Optional[float] = None
    cost_basis_per_share: Optional[float] = None
    account: Optional[str] = None
    notes: Optional[str] = None


class PositionCloseRequest(BaseModel):
    closing_price: float = Field(gt=0)
    closed_at: Optional[str] = None


@router.get("/positions", response_model=List[Position])
def list_positions(include_closed: bool = False) -> List[Position]:
    return [Position(**p) for p in storage.list_positions(include_closed=include_closed)]


@router.post("/positions", response_model=Position)
async def create_position(req: PositionCreateRequest) -> Position:
    pid = storage.add_position(
        ticker=req.ticker,
        shares=req.shares,
        cost_basis_per_share=req.cost_basis_per_share,
        opened_at=req.opened_at,
        account=req.account,
        notes=req.notes,
    )
    # Warm the price stream so summary shows live value immediately.
    try:
        await broadcaster.subscribe("price", req.ticker)
    except Exception:
        pass
    row = storage.get_position(pid)
    if not row:
        raise HTTPException(status_code=500, detail="position not retrievable")
    return Position(**row)


@router.put("/positions/{pid}", response_model=Position)
def update_position(pid: int, req: PositionUpdateRequest) -> Position:
    if not storage.get_position(pid):
        raise HTTPException(status_code=404, detail="position not found")
    storage.update_position(
        pid,
        shares=req.shares,
        cost_basis_per_share=req.cost_basis_per_share,
        account=req.account,
        notes=req.notes,
    )
    return Position(**storage.get_position(pid))


@router.post("/positions/{pid}/close", response_model=Position)
def close_position(pid: int, req: PositionCloseRequest) -> Position:
    if not storage.get_position(pid):
        raise HTTPException(status_code=404, detail="position not found")
    storage.close_position(pid, closing_price=req.closing_price, closed_at=req.closed_at)
    return Position(**storage.get_position(pid))


@router.delete("/positions/{pid}")
def delete_position(pid: int) -> dict:
    storage.delete_position(pid)
    return {"deleted": pid}


@router.get("/summary")
def summary() -> dict:
    """Aggregate open positions with live-price valuation.

    Returns total cost, current value, unrealized P&L (+ %), and a per-position
    breakdown. Closed positions get realized P&L summed separately.
    """
    open_positions = storage.list_positions(include_closed=False)
    closed_positions = [
        p for p in storage.list_positions(include_closed=True)
        if p.get("closed_at")
    ]

    rows = []
    total_cost = 0.0
    total_value = 0.0
    for p in open_positions:
        ticker = p["ticker"]
        cost = p["shares"] * p["cost_basis_per_share"]
        st = broadcaster._state.get(ticker)
        live_price = st.last_price if st else None
        value = (p["shares"] * live_price) if live_price else None
        unreal = (value - cost) if value is not None else None
        unreal_pct = (unreal / cost * 100) if (unreal is not None and cost) else None
        rows.append({
            **p,
            "cost": cost,
            "live_price": live_price,
            "value": value,
            "unrealized": unreal,
            "unrealized_pct": unreal_pct,
        })
        total_cost += cost
        if value is not None:
            total_value += value

    realized = 0.0
    for p in closed_positions:
        if p.get("closing_price") is None:
            continue
        cost = p["shares"] * p["cost_basis_per_share"]
        proceeds = p["shares"] * p["closing_price"]
        realized += (proceeds - cost)

    return {
        "open_positions": rows,
        "total_cost": total_cost,
        "total_value": total_value,
        "unrealized_pnl": total_value - total_cost if total_value else None,
        "unrealized_pnl_pct": ((total_value - total_cost) / total_cost * 100) if total_cost else None,
        "realized_pnl": realized,
        "open_count": len(open_positions),
        "closed_count": len(closed_positions),
    }
