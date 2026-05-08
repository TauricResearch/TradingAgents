"""Watchlist CRUD + a /watchlist/quotes batch fetch endpoint."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from gui import storage
from service.streaming import broadcaster

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


class WatchlistEntry(BaseModel):
    id: int
    ticker: str
    added_at: str
    notes: Optional[str] = None


class WatchlistAddRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=32)
    notes: Optional[str] = None


@router.get("", response_model=List[WatchlistEntry])
def list_watchlist() -> List[WatchlistEntry]:
    return [WatchlistEntry(**e) for e in storage.list_watchlist()]


@router.post("", response_model=WatchlistEntry)
async def add_to_watchlist(req: WatchlistAddRequest) -> WatchlistEntry:
    entry = storage.add_to_watchlist(req.ticker, req.notes)
    # Pre-warm: register the ticker with the broadcaster so the next poll
    # picks it up. The first browser subscription would do this anyway,
    # but doing it now means a snapshot is ready by the time the UI loads.
    await broadcaster.subscribe("price", entry["ticker"])
    return WatchlistEntry(**entry)


@router.delete("/{ticker}")
def remove_from_watchlist(ticker: str) -> dict:
    storage.remove_from_watchlist(ticker)
    return {"removed": ticker.upper()}


@router.get("/quotes")
def watchlist_quotes() -> dict:
    """Last-known quote snapshot for every ticker in the watchlist —
    cheap REST endpoint suitable for periodic UI refresh fallback when
    a client doesn't want to maintain live WebSockets per row."""
    out: dict[str, dict[str, float | None] | None] = {}
    for entry in storage.list_watchlist():
        ticker = entry["ticker"]
        st = broadcaster._state.get(ticker)
        if st and st.last_price is not None:
            out[ticker] = {
                "price": st.last_price,
                "change": st.last_change,
                "change_pct": st.last_change_pct,
                "polled_at": st.last_polled,
            }
        else:
            out[ticker] = None
    return out
