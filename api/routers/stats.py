import datetime

from fastapi import APIRouter, Request

from api.auth import get_user_claims_async
from api.database import get_db_connection
from api.models import StatsResponse

router = APIRouter(tags=["stats"])


@router.get("/signals-ms/stats", response_model=StatsResponse)
async def get_stats(request: Request):
    await get_user_claims_async(request)  # auth required, no quota cost

    today = datetime.datetime.now().date().isoformat()
    conn = get_db_connection()
    try:
        rows = conn.execute(
            "SELECT signal_type, confidence FROM trading_signals WHERE generated_at >= ?",
            (today,),
        ).fetchall()

        signals_today = len(rows)
        buy = sum(1 for r in rows if r["signal_type"] in ("buy", "overweight"))
        sell = sum(1 for r in rows if r["signal_type"] in ("sell", "underweight"))
        hold = sum(1 for r in rows if r["signal_type"] == "hold")
        avg_conf = (
            round(sum(r["confidence"] for r in rows) / signals_today, 2)
            if signals_today
            else 0.0
        )
        watchlist_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM watchlist_tickers"
        ).fetchone()["cnt"]

        return StatsResponse(
            signals_today=signals_today,
            buy_signals=buy,
            sell_signals=sell,
            hold_signals=hold,
            avg_confidence=avg_conf,
            active_watchlist=watchlist_count,
        )
    finally:
        conn.close()
