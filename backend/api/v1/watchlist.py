from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.core.db import get_db
from backend.core.deps import get_current_user
from backend.integrations.india import normalize_india_symbol
from backend.integrations.market_data import get_market_provider
from backend.models import Analysis, User, WatchlistItem
from backend.schemas import WatchlistCreate
from backend.services.serialize import serialize_analysis

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


@router.get("")
def list_watchlist(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    items = db.query(WatchlistItem).filter(WatchlistItem.user_id == user.id).all()
    provider = get_market_provider()
    out = []
    for item in items:
        quote = None
        try:
            quote = provider.quote(item.symbol)
        except Exception:
            quote = None
        latest = (
            db.query(Analysis)
            .filter(Analysis.user_id == user.id, Analysis.symbol == item.symbol)
            .order_by(Analysis.created_at.desc())
            .first()
        )
        out.append(
            {
                "id": item.id,
                "symbol": item.symbol,
                "quote": quote.model_dump() if quote else None,
                "last_analysis": serialize_analysis(latest, include_payload=False).model_dump() if latest else None,
            }
        )
    return {"items": out}


@router.post("")
def add_watchlist(body: WatchlistCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    symbol, _ = normalize_india_symbol(body.symbol)
    existing = (
        db.query(WatchlistItem)
        .filter(WatchlistItem.user_id == user.id, WatchlistItem.symbol == symbol)
        .first()
    )
    if existing:
        return {"id": existing.id, "symbol": existing.symbol}
    item = WatchlistItem(user_id=user.id, symbol=symbol)
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"id": item.id, "symbol": item.symbol}


@router.delete("/{item_id}")
def remove_watchlist(item_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    item = db.get(WatchlistItem, item_id)
    if not item or item.user_id != user.id:
        raise HTTPException(status_code=404, detail="Watchlist item not found")
    db.delete(item)
    db.commit()
    return {"ok": True}
