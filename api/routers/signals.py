from typing import Optional

from fastapi import APIRouter, Query, Request

from api.auth import enforce_quota, get_user_claims_async
from api.database import get_db_connection, _row_to_signal
from api.models import SignalsResponse
from api.signals_engine import mask_signal

router = APIRouter(tags=["signals"])


@router.get("/signals-ms/signals", response_model=SignalsResponse)
async def get_signals_feed(
    request: Request,
    ticker: Optional[str] = Query(None),
    signal_type: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    user_id, tier = await get_user_claims_async(request)
    entitlement = enforce_quota(user_id, tier, log_view=True)

    parts = ["SELECT * FROM trading_signals WHERE 1=1"]
    params: list = []

    if ticker:
        parts.append("AND ticker = ?")
        params.append(ticker.upper())
    if signal_type:
        parts.append("AND signal_type = ?")
        params.append(signal_type.lower())
    if start_date:
        parts.append("AND generated_at >= ?")
        params.append(start_date)
    if end_date:
        parts.append("AND generated_at <= ?")
        params.append(end_date)

    parts.append("ORDER BY generated_at DESC LIMIT ? OFFSET ?")
    params.extend([limit, offset])

    conn = get_db_connection()
    try:
        rows = conn.execute(" ".join(parts), tuple(params)).fetchall()
        signals = [
            mask_signal(_row_to_signal(r)) if entitlement.locked else _row_to_signal(r)
            for r in rows
        ]
        return SignalsResponse(signals=signals, entitlement=entitlement)
    finally:
        conn.close()


@router.get("/signals-ms/signals/latest", response_model=SignalsResponse)
async def get_latest_signals(request: Request):
    user_id, tier = await get_user_claims_async(request)
    entitlement = enforce_quota(user_id, tier, log_view=True)

    conn = get_db_connection()
    try:
        rows = conn.execute("""
            SELECT s1.* FROM trading_signals s1
            INNER JOIN (
                SELECT ticker, MAX(generated_at) as max_gen
                FROM trading_signals GROUP BY ticker
            ) s2 ON s1.ticker = s2.ticker AND s1.generated_at = s2.max_gen
            ORDER BY s1.ticker ASC
        """).fetchall()
        signals = [
            mask_signal(_row_to_signal(r)) if entitlement.locked else _row_to_signal(r)
            for r in rows
        ]
        return SignalsResponse(signals=signals, entitlement=entitlement)
    finally:
        conn.close()
