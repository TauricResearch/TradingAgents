import datetime

from fastapi import APIRouter, HTTPException, Request

from api.auth import get_user_claims_async
from api.database import get_db_connection
from api.models import UserWatchlistPayload

router = APIRouter(tags=["watchlist"])


@router.get("/signals-ms/watchlist")
async def get_user_watchlist(request: Request):
    user_id, _ = await get_user_claims_async(request)
    conn = get_db_connection()
    try:
        rows = conn.execute(
            "SELECT ticker, asset_type, added_at FROM user_watchlist WHERE user_id = ? ORDER BY added_at DESC",
            (user_id,),
        ).fetchall()
        return {"watchlist": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.post("/signals-ms/watchlist", status_code=201)
async def add_to_user_watchlist(payload: UserWatchlistPayload, request: Request):
    user_id, _ = await get_user_claims_async(request)
    ticker = payload.ticker.strip().upper()
    asset_type = payload.asset_type.strip().lower()
    if asset_type not in ("stocks", "crypto"):
        raise HTTPException(
            status_code=400, detail="asset_type must be 'stocks' or 'crypto'"
        )
    conn = get_db_connection()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO user_watchlist (user_id, ticker, asset_type, added_at) VALUES (?, ?, ?, ?)",
            (
                user_id,
                ticker,
                asset_type,
                datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        conn.commit()
        return {"status": "success", "ticker": ticker}
    finally:
        conn.close()


@router.delete("/signals-ms/watchlist/{ticker}")
async def remove_from_user_watchlist(ticker: str, request: Request):
    user_id, _ = await get_user_claims_async(request)
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            "DELETE FROM user_watchlist WHERE user_id = ? AND ticker = ?",
            (user_id, ticker.upper()),
        )
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(
                status_code=404, detail=f"{ticker.upper()} not in your watchlist"
            )
        return {"status": "success"}
    finally:
        conn.close()
