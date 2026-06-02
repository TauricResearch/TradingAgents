"""Backfill raw_return / alpha_return for completed analyses."""
import logging
from datetime import date, datetime, timedelta

_logger = logging.getLogger(__name__)

# Positive-signal families that we expect to go UP
_BUY_SIGNALS = {"Buy", "Overweight"}
_SELL_SIGNALS = {"Sell", "Underweight"}

HOLDING_DAYS = 5  # days to hold after signal for return calculation


async def backfill_returns(db) -> int:
    """Update raw_return / alpha_return for analyses old enough to have outcome data.

    Returns the number of rows updated.
    """
    from sqlalchemy import select
    from backend.models.analysis import AnalysisResult

    cutoff = (datetime.utcnow() - timedelta(days=HOLDING_DAYS + 2)).strftime("%Y-%m-%d")
    result = await db.execute(
        select(AnalysisResult)
        .where(AnalysisResult.raw_return.is_(None))
        .where(AnalysisResult.signal.isnot(None))
        .where(AnalysisResult.trade_date <= cutoff)
        .limit(50)
    )
    rows = result.scalars().all()
    updated = 0
    for row in rows:
        raw, alpha, days = await _fetch_returns_async(row.ticker, row.trade_date)
        if raw is not None:
            row.raw_return = raw
            row.alpha_return = alpha
            row.holding_days = days
            updated += 1
    if updated:
        await db.commit()
    _logger.info("Performance backfill: updated %d rows", updated)
    return updated


async def _fetch_returns_async(ticker: str, trade_date: str, holding_days: int = HOLDING_DAYS):
    import asyncio
    return await asyncio.to_thread(_fetch_returns_sync, ticker, trade_date, holding_days)


def _fetch_returns_sync(ticker: str, trade_date: str, holding_days: int = HOLDING_DAYS):
    try:
        import yfinance as yf
        start = datetime.strptime(trade_date, "%Y-%m-%d")
        end = start + timedelta(days=holding_days + 7)
        end_str = end.strftime("%Y-%m-%d")

        stock = yf.Ticker(ticker).history(start=trade_date, end=end_str)
        bench = yf.Ticker("SPY").history(start=trade_date, end=end_str)
        if len(stock) < 2 or len(bench) < 2:
            return None, None, None
        actual = min(holding_days, len(stock) - 1, len(bench) - 1)
        raw = float((stock["Close"].iloc[actual] - stock["Close"].iloc[0]) / stock["Close"].iloc[0])
        bench_r = float((bench["Close"].iloc[actual] - bench["Close"].iloc[0]) / bench["Close"].iloc[0])
        return round(raw, 4), round(raw - bench_r, 4), actual
    except Exception as exc:
        _logger.debug("Return fetch failed %s %s: %s", ticker, trade_date, exc)
        return None, None, None
