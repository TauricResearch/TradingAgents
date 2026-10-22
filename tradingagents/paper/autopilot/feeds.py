"""Forward-only market/earnings adapters for a brokerless paper simulator.

Historical Yahoo OHLC are fetched only AFTER today's closed trading session;
pre-open and pre-close earnings snapshots have to be captured BEFORE their
respective cutoffs. Never turn data fetched late into alleged earlier evidence.
"""
from __future__ import annotations

import json
import re
import time
from datetime import date, datetime, time as clock_time, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from tradingagents.paper.conditional import EarningsSnapshot
from tradingagents.paper.engine import Bar

NY = ZoneInfo("America/New_York")


def ny_now(now: datetime | None = None) -> datetime:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Clock must be timezone-aware")
    return value.astimezone(NY)


def session_cutoff(now: datetime, phase: str) -> str:
    """Demand a REAL wall-clock window; external caller cannot backdate an event."""
    local = ny_now(now)
    current = local.time().replace(tzinfo=None)
    start, end = {
        "preopen": (clock_time(8, 45), clock_time(9, 25)),
        "preclose": (clock_time(17, 0), clock_time(17, 25)),
        "close": (clock_time(17, 40), clock_time(23, 59, 59)),
    }[phase]
    if local.weekday() >= 5 or not start <= current <= end:
        raise ValueError(f"{phase} is outside its New York session window")
    return local.date().isoformat()


def _yahoo_earnings(ticker: str, session: str) -> tuple[str | None, str | None]:
    """Yahoo's datetime-indexed earnings calendar (upcoming and previous)."""
    from tradingagents.dataflows.vendor_gateway import get_yahoo_ticker

    frame = get_yahoo_ticker(ticker).get_earnings_dates(limit=20)
    if frame is None or frame.empty:
        return None, None
    dates = sorted(set(ts.date().isoformat() for ts in frame.index if hasattr(ts, "date")))
    past = [d for d in dates if d < session]
    future = [d for d in dates if d >= session]
    return max(past) if past else None, min(future) if future else None


def _nasdaq_next_date(ticker: str, next_date: str) -> bool:
    """Cross-check Yahoo's upcoming earnings date in Nasdaq's public calendar.

    Response format / coverage can change. Any HTTP, parser or coverage problem
    is an explicit UNVERIFIED result, never a guessed all-clear.
    """
    from urllib.parse import urlsplit
    if not re.fullmatch(r"[A-Z0-9.-]{1,12}", ticker):
        return False
    target = "https://api.nasdaq.com/api/calendar/earnings?" + urlencode({"date": next_date})
    request = Request(target, headers={
        "User-Agent": "Mozilla/5.0 (KoralEquities Paper Research; no brokerage)",
        "Accept": "application/json", "Origin": "https://www.nasdaq.com",
        "Referer": "https://www.nasdaq.com/market-activity/earnings",
    })
    with urlopen(request, timeout=12) as r:
        obj = json.loads(r.read(1_000_000).decode("utf-8"))
    rows = (obj.get("data") or {}).get("rows") or []
    if not isinstance(rows, list):
        return False
    return any(isinstance(r, dict) and str(r.get("symbol") or r.get("ticker") or "").upper() == ticker
               for r in rows)


def earnings_for(ticker: str, session: str, now: datetime) -> EarningsSnapshot:
    """A genuinely collected observation, not a historical/issuer-authorised truth.

    verified=True means TWO secondary calendar feeds agree on the NEXT date;
    the previous event must exist from Yahoo. The field does not certify an
    issuer's primary IR release. False returns block opening new positions.
    """
    observed = now.astimezone(timezone.utc).isoformat()
    try:
        last, upcoming = _yahoo_earnings(ticker, session)
        if not last or not upcoming or not _nasdaq_next_date(ticker, upcoming):
            raise ValueError("Missing or unmatched issuer earnings event calendar")
        return EarningsSnapshot(session, upcoming, last, "YAHOO+NASDAQ_CONSENSUS_SECONDARY",
                                True, observed)
    except Exception:
        return EarningsSnapshot(session, None, None, "UNVERIFIED_EARNINGS_SOURCE", False, observed)


def unknown_earnings(session: str, now: datetime, why: str = "NOT_CAPTURED_AT_CUTOFF") -> EarningsSnapshot:
    return EarningsSnapshot(session, None, None, why, False,
                            now.astimezone(timezone.utc).isoformat())


def capture_earnings(home: Path, session: str, phase: str,
                     symbols: list[str], now: datetime,
                     source=earnings_for) -> Path:
    """Immutable per-day per-phase snapshots; never overwrite original evidence."""
    if phase not in ("preopen", "preclose"):
        raise ValueError("Unknown earnings phase")
    if session != session_cutoff(now, phase):
        raise ValueError("Session date does not match current real-world cutoff")
    path = home / "calendar" / session / (phase + ".json")
    if path.exists():
        raise ValueError("Earnings snapshot already captured; no retroactive revisions")
    from dataclasses import asdict
    observations = {ticker: asdict(source(ticker, session, now)) for ticker in sorted(set(symbols))}
    data = {"session": session, "phase": phase, "observed_utc": now.astimezone(timezone.utc).isoformat(),
            "earnings": observations, "source_policy": "TWO_SECONDARY_FEEDS_MUST_AGREE_OR_BLOCK"}
    path.parent.mkdir(parents=True, exist_ok=True)
    from tradingagents.paper.autopilot.state import fingerprint
    payload = json.dumps(data, sort_keys=True, indent=2, allow_nan=False)
    # Exclusive creation makes it impossible for two simultaneous runs to overwrite evidence.
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(payload + "\n")
    except FileExistsError:
        raise ValueError("Concurrent earnings snapshot exists") from None
    return path


def read_earnings(home: Path, session: str, phase: str,
                  tickers: set[str], now: datetime) -> dict[str, EarningsSnapshot]:
    """Missing or corrupt observation => explicit block; never infer no earnings."""
    file = home / "calendar" / session / (phase + ".json")
    raw = {}
    try:
        snapshot = json.loads(file.read_text(encoding="utf-8"))
        if (snapshot.get("session") != session or snapshot.get("phase") != phase or
                snapshot.get("source_policy") != "TWO_SECONDARY_FEEDS_MUST_AGREE_OR_BLOCK"):
            raise ValueError("Wrong session snapshot")
        raw = snapshot.get("earnings") or {}
    except (OSError, KeyError, ValueError, TypeError, json.JSONDecodeError):
        pass
    output = {}
    for ticker in tickers:
        try:
            x = raw[ticker]
            if set(x) != {"asof_date", "next_earnings_date", "last_earnings_date", "source", "verified", "observed_at_utc"}:
                raise ValueError("Unexpected earnings schema")
            obs = EarningsSnapshot(**x)
            if obs.asof_date != session or obs.verified not in (True, False):
                raise ValueError("Invalid calendar evidence")
        except (KeyError, TypeError, ValueError):
            obs = unknown_earnings(session, now)
        output[ticker] = obs
    return output


def fetch_session_prices(symbols: set[str], start: str, end: str):
    """Prices from existing validated provider; always include SPY and GBPUSD."""
    from tradingagents.paper.cli import fetch_daily, forex_for_day
    tickers = sorted(symbols | {"SPY", "GBPUSD=X"})
    quotes = fetch_daily(tickers, start, end, required=set(tickers))
    if "SPY" not in quotes:
        raise ValueError("Missing benchmark data; session cannot be marked")
    return quotes, forex_for_day


def reject_unmodelled_corporate_actions(symbols: set[str], start: str, end: str,
                                       history_provider=None) -> None:
    """Conservative guard on corporate-action accounting for all at-risk stocks.

    The baseline simulator does not adjust held quantity/cash across share
    splits, special distributions or dividends. On a current affected session,
    prefer NO simulated fill/mark to a fabricated stop loss or return.
    A proper next release needs split-adjusted shares and cash pay dates.
    """
    if history_provider is None:
        from tradingagents.dataflows.vendor_gateway import get_yahoo_ticker
        history_provider = lambda ticker, start_, end_: get_yahoo_ticker(ticker).history(
            start=start_, end=end_, interval="1d", auto_adjust=False, actions=True)
    request = history_provider
    last = (date.fromisoformat(end) + timedelta(days=1)).isoformat()
    for symbol in sorted(symbols):
        if symbol in ("SPY", "GBPUSD=X"):
            continue
        frame = request(symbol, start, last)
        if frame is None or frame.empty:
            raise ValueError(f"Corporate action metadata unavailable for required {symbol}")
        if "Stock Splits" not in frame.columns or "Dividends" not in frame.columns:
            raise ValueError(f"Corporate action fields unavailable for required {symbol}")
        for stamp, row in frame.iterrows():
            day = stamp.date().isoformat()
            if start <= day <= end:
                split = float(row["Stock Splits"])
                div = float(row["Dividends"])
                if not (-1e10 < div < 1e10) or not (0 <= split < 1e10):
                    raise ValueError(f"Invalid corporate-action value on {day} for {symbol}")
                if split != 0 or div != 0:
                    raise ValueError(f"UNMODELLED_CORPORATE_ACTION {symbol} {day}: split={split}, cash_dividend={div}; do not invent adjusted shares or cash")
