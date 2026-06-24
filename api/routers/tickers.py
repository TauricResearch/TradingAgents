import datetime

from fastapi import APIRouter, HTTPException, Request

from api.auth import enforce_quota, get_user_claims_async
from api.database import get_db_connection
from api.models import TickerStats, TickersResponse, WatchlistAddPayload

router = APIRouter(tags=["tickers"])


@router.get("/signals-ms/tickers", response_model=TickersResponse)
async def get_tracked_tickers(request: Request):
    user_id, tier = await get_user_claims_async(request)
    entitlement = enforce_quota(user_id, tier, log_view=False)

    conn = get_db_connection()
    try:
        rows = conn.execute("""
            SELECT w.ticker, w.asset_type, w.added_at,
                   COUNT(s.id) as signals_count, MAX(s.generated_at) as last_signal_at
            FROM watchlist_tickers w
            LEFT JOIN trading_signals s ON w.ticker = s.ticker
            GROUP BY w.ticker ORDER BY w.ticker ASC
        """).fetchall()

        tickers = []
        for row in rows:

            def _parse_dt(s):
                if not s:
                    return None
                fmt = "%Y-%m-%d %H:%M:%S" if "." not in s else "%Y-%m-%d %H:%M:%S.%f"
                return datetime.datetime.strptime(s, fmt)

            tickers.append(
                TickerStats(
                    ticker=row["ticker"],
                    asset_type=row["asset_type"],
                    added_at=_parse_dt(row["added_at"]),
                    signals_count=row["signals_count"],
                    last_signal_at=_parse_dt(row["last_signal_at"]),
                )
            )

        return TickersResponse(tickers=tickers, entitlement=entitlement)
    finally:
        conn.close()


@router.post("/signals-ms/tickers", status_code=201)
def add_watchlist_ticker(payload: WatchlistAddPayload):
    ticker = payload.ticker.strip().upper()
    asset_type = payload.asset_type.strip().lower()
    if asset_type not in ("stocks", "crypto"):
        raise HTTPException(
            status_code=400, detail="asset_type must be 'stocks' or 'crypto'"
        )
    conn = get_db_connection()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO watchlist_tickers (ticker, asset_type, added_at) VALUES (?, ?, ?)",
            (ticker, asset_type, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()
        return {"status": "success", "ticker": ticker}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.delete("/signals-ms/tickers/{ticker}")
def delete_watchlist_ticker(ticker: str):
    ticker = ticker.strip().upper()
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            "DELETE FROM watchlist_tickers WHERE ticker = ?", (ticker,)
        )
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"{ticker} not in watchlist")
        return {"status": "success", "ticker": ticker}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
