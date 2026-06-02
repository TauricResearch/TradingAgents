"""Market data API — OHLCV price data for charting."""
import io
import logging
from datetime import datetime, timedelta

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query

from backend.core.security import get_current_user

_logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/market", tags=["market"])


def _date_range(period: str) -> tuple[str, str]:
    """Convert period string to (start_date, end_date)."""
    end = datetime.now()
    delta_map = {
        "1m": timedelta(days=31),
        "3m": timedelta(days=92),
        "6m": timedelta(days=183),
        "1y": timedelta(days=365),
        "2y": timedelta(days=730),
        "5y": timedelta(days=1825),
    }
    delta = delta_map.get(period, timedelta(days=365))
    start = end - delta
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


@router.get("/ohlcv")
async def get_ohlcv(
    ticker: str = Query(..., description="Ticker symbol, e.g. AAPL"),
    start_date: str = Query(None, description="YYYY-MM-DD"),
    end_date: str = Query(None, description="YYYY-MM-DD"),
    period: str = Query("1y", description="1m|3m|6m|1y|2y|5y — ignored when start_date provided"),
    _: dict = Depends(get_current_user),
):
    """Return OHLCV candlestick data for lightweight-charts."""
    ticker = ticker.upper().strip()

    if start_date and end_date:
        s, e = start_date, end_date
    else:
        s, e = _date_range(period)

    # Validate dates
    try:
        datetime.strptime(s, "%Y-%m-%d")
        datetime.strptime(e, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Tarih formatı YYYY-MM-DD olmalı")

    try:
        import yfinance as yf

        data = yf.Ticker(ticker).history(start=s, end=e)
        if data.empty:
            raise HTTPException(status_code=404, detail=f"{ticker} için veri bulunamadı")

        if data.index.tz is not None:
            data.index = data.index.tz_localize(None)

        candles = []
        for ts, row in data.iterrows():
            candles.append({
                "time": ts.strftime("%Y-%m-%d"),
                "open": round(float(row["Open"]), 2),
                "high": round(float(row["High"]), 2),
                "low": round(float(row["Low"]), 2),
                "close": round(float(row["Close"]), 2),
                "volume": int(row.get("Volume", 0)),
            })

        return {"ticker": ticker, "start_date": s, "end_date": e, "candles": candles}

    except HTTPException:
        raise
    except Exception as exc:
        _logger.error("OHLCV fetch failed %s: %s", ticker, exc)
        raise HTTPException(status_code=500, detail=str(exc))
