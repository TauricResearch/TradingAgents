"""Calendar of upcoming + recent events: earnings, dividends, your runs.

    GET /calendar?from=YYYY-MM-DD&to=YYYY-MM-DD&tickers=AAPL,MSFT
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import List, Optional

import pandas as pd
import yfinance as yf
from fastapi import APIRouter, Query
from pydantic import BaseModel

from gui import storage

router = APIRouter(prefix="/calendar", tags=["calendar"])


class CalendarEvent(BaseModel):
    date: str
    ticker: Optional[str] = None
    kind: str       # earnings | dividend | run | ex_dividend
    title: str
    detail: Optional[str] = None
    payload: Optional[dict] = None


def _to_iso(d) -> Optional[str]:
    if d is None:
        return None
    if isinstance(d, str):
        return d[:10]
    if hasattr(d, "isoformat"):
        return d.isoformat()[:10]
    if hasattr(d, "strftime"):
        return d.strftime("%Y-%m-%d")
    return None


def _earnings_for(ticker: str) -> List[CalendarEvent]:
    """Pull next earnings date(s) from yfinance.

    yfinance exposes the calendar in two shapes depending on version:
    a dict (new) and a DataFrame (older). Handle both.
    """
    out: List[CalendarEvent] = []
    try:
        cal = yf.Ticker(ticker).calendar
    except Exception:
        return out
    if cal is None:
        return out

    if isinstance(cal, dict):
        dates = cal.get("Earnings Date") or cal.get("earningsDate")
        if isinstance(dates, list):
            for d in dates:
                iso = _to_iso(d)
                if iso:
                    out.append(CalendarEvent(
                        date=iso, ticker=ticker, kind="earnings",
                        title=f"{ticker} earnings",
                    ))
    elif isinstance(cal, pd.DataFrame) and not cal.empty:
        # Old shape: DataFrame with "Earnings Date" row.
        try:
            row = cal.loc["Earnings Date"]
            for v in row.values.flatten():
                iso = _to_iso(v)
                if iso:
                    out.append(CalendarEvent(
                        date=iso, ticker=ticker, kind="earnings",
                        title=f"{ticker} earnings",
                    ))
        except Exception:
            pass
    return out


def _dividends_for(ticker: str, start: date, end: date) -> List[CalendarEvent]:
    out: List[CalendarEvent] = []
    try:
        ser = yf.Ticker(ticker).dividends
    except Exception:
        return out
    if ser is None or len(ser) == 0:
        return out
    if hasattr(ser.index, "tz") and ser.index.tz is not None:
        ser.index = ser.index.tz_localize(None)
    s_start = pd.Timestamp(start)
    s_end = pd.Timestamp(end)
    sub = ser[(ser.index >= s_start) & (ser.index <= s_end)]
    for ts, amount in sub.items():
        iso = ts.strftime("%Y-%m-%d")
        out.append(CalendarEvent(
            date=iso, ticker=ticker, kind="dividend",
            title=f"{ticker} dividend",
            detail=f"${float(amount):.4f} / share",
            payload={"amount": float(amount)},
        ))
    return out


def _runs_in_range(start: date, end: date, tickers: Optional[List[str]] = None
                   ) -> List[CalendarEvent]:
    out: List[CalendarEvent] = []
    rows = storage.list_runs(limit=10_000)
    for r in rows:
        td = r.get("trade_date") or ""
        try:
            td_d = datetime.strptime(td, "%Y-%m-%d").date()
        except ValueError:
            continue
        if td_d < start or td_d > end:
            continue
        if tickers and r["ticker"] not in tickers:
            continue
        out.append(CalendarEvent(
            date=td,
            ticker=r["ticker"],
            kind="run",
            title=f"{r['ticker']} analysis",
            detail=f"decision: {r.get('decision') or '—'}",
            payload={"run_id": r["run_id"], "status": r.get("status")},
        ))
    return out


@router.get("", response_model=List[CalendarEvent])
def calendar(
    from_: str = Query(..., alias="from", description="YYYY-MM-DD"),
    to: str = Query(..., description="YYYY-MM-DD"),
    tickers: Optional[str] = Query(None, description="Comma-separated tickers; default = watchlist"),
    include_runs: bool = True,
    include_earnings: bool = True,
    include_dividends: bool = True,
) -> List[CalendarEvent]:
    start = datetime.strptime(from_, "%Y-%m-%d").date()
    end = datetime.strptime(to, "%Y-%m-%d").date()

    if tickers:
        tlist = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    else:
        tlist = [w["ticker"] for w in storage.list_watchlist()]

    events: List[CalendarEvent] = []

    if include_earnings:
        for t in tlist:
            events.extend(_earnings_for(t))

    if include_dividends:
        for t in tlist:
            events.extend(_dividends_for(t, start, end))

    if include_runs:
        events.extend(_runs_in_range(start, end, tlist if tlist else None))

    # Filter to range and sort.
    out = []
    for e in events:
        try:
            e_d = datetime.strptime(e.date, "%Y-%m-%d").date()
        except ValueError:
            continue
        if start <= e_d <= end:
            out.append(e)
    out.sort(key=lambda e: (e.date, e.kind, e.ticker or ""))
    return out
