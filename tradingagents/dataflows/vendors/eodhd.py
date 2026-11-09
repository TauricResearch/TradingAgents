"""Opt-in daily US price snapshots. No fallback, live quotes, or adjusted OHLC claims."""

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from tradingagents.dataflows.files import locked, replace_file
from tradingagents.dataflows.net import get_scrubbed


class EODHDError(RuntimeError):
    """Safe vendor failure without request URLs, response bodies, or credentials."""


@dataclass
class DailySnapshot:
    bars: pd.DataFrame
    metadata: dict


def _day(value):
    day = pd.Timestamp(value)
    if not isinstance(day, pd.Timestamp) or day.tzinfo is not None or day != day.normalize():
        raise ValueError("Expected an unzoned session date (YYYY-MM-DD)")
    return day


def _calendar(start, end):
    # Optional import keeps the existing graph/CLI dependency surface unchanged.
    import exchange_calendars as xcals

    return xcals.get_calendar(
        "XNYS", start=start - pd.Timedelta(days=10), end=end + pd.Timedelta(days=10)
    )


def normalize_daily(rows, start, end, as_of) -> DailySnapshot:
    """Use raw OHLCV and calendar close timestamps; never fill absent sessions.

    adjusted_close is retained as vendor data, not converted into adjusted OHLC.
    Price-scale discontinuities block detector windows. This cannot recover the
    corporate-action information available at a historical decision time.
    """
    start, end = _day(start), _day(end)
    as_of = pd.Timestamp(as_of)
    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone aware")
    if end < start:
        raise ValueError("End precedes start")
    if not isinstance(rows, list) or not rows:
        raise EODHDError("EODHD returned no daily bars")
    frame = pd.DataFrame(rows)
    required = {"date", "open", "high", "low", "close", "volume", "adjusted_close"}
    if not required.issubset(frame.columns):
        raise EODHDError("EODHD response lacks required daily fields")
    try:
        dates = frame["date"].map(_day)
        if dates.duplicated().any():
            raise ValueError("duplicate session")
        frame = frame.assign(session=dates).sort_values("session")
        for column in required - {"date"}:
            frame[column] = pd.to_numeric(frame[column], errors="raise")
        numeric = frame[list(required - {"date"})]
        if (
            numeric.isna().any().any()
            or not numeric.map(lambda x: float("-inf") < x < float("inf")).all().all()
        ):
            raise ValueError("non-finite value")
        if (
            (frame[["open", "high", "low", "close", "adjusted_close"]] <= 0).any().any()
            or (frame.volume < 0).any()
            or (frame.high < frame[["open", "close", "low"]].max(axis=1)).any()
            or (frame.low > frame[["open", "close", "high"]].min(axis=1)).any()
        ):
            raise ValueError("invalid OHLCV")
    except (ValueError, TypeError, OverflowError):
        raise EODHDError("EODHD returned malformed daily OHLCV") from None
    calendar = _calendar(start, end)
    sessions = calendar.sessions_in_range(start, end)
    closes = {s.tz_localize(None): calendar.session_close(s) for s in sessions}
    frame = frame[frame.session.between(start, end)].copy()
    if not frame.session.isin(closes).all():
        raise EODHDError("EODHD returned a bar outside a US market session")
    completed = {s: c for s, c in closes.items() if c <= as_of}
    frame = frame[frame.session.isin(completed)].copy()
    if frame.empty:
        raise EODHDError("No completed daily bars in the requested window")
    frame.index = pd.DatetimeIndex(frame.session.map(completed), name="timestamp")
    factor = frame.adjusted_close / frame.close
    frame["adjustment_break"] = factor.pct_change().abs().gt(0.001)
    # A missing scheduled session blocks a pattern window, rather than fabricating a bar.
    positions = {s: i for i, s in enumerate(completed)}
    frame["gap_before"] = frame.session.map(positions).diff().gt(1)
    missing = sorted(set(completed) - set(frame.session))
    frame["session"] = frame.session.dt.strftime("%Y-%m-%d")
    frame = frame.drop(columns="date")
    return DailySnapshot(
        frame,
        {
            "source": "EODHD",
            "interval": "1d",
            "timezone": "UTC",
            "exchange_calendar": "XNYS",
            "price_basis": "raw OHLCV; vendor adjusted_close retained",
            "retrieved_at": as_of.isoformat(),
            "last_completed_bar": frame.index[-1].isoformat(),
            "last_expected_bar": max(completed.values()).isoformat(),
            "data_age_seconds": max(0.0, (as_of - frame.index[-1]).total_seconds()),
            "missing_sessions": [s.strftime("%Y-%m-%d") for s in missing],
            "freshness": "missing sessions at retrieval"
            if missing
            else "complete requested sessions at retrieval",
            "point_in_time_certified": False,
            "warning": "Historical/delayed data. Retrieval time is not publication time. "
            "Revised history and corporate actions are not point-in-time certified.",
        },
    )


class EODHDClient:
    """One request per snapshot with TTL caching; refresh replaces the entire window.

    Full replacement prevents mixing old raw bars and newly revised adjustments.
    Incremental corporate-action-safe updates and intraday are a later increment.
    Rate/entitlement errors stop immediately; no hidden retries or vendor fallback.
    """

    def __init__(self, cache_dir: Path, *, ttl_seconds=21600, min_request_seconds=1.1):
        if ttl_seconds < 0 or min_request_seconds < 0:
            raise ValueError("Cache TTL and request spacing must be nonnegative")
        self.cache_dir = Path(cache_dir)
        self.ttl_seconds = ttl_seconds
        self.min_request_seconds = min_request_seconds
        self._last_request = 0.0

    def daily(self, symbol: str, start: str, end: str, *, refresh=False, now=None):
        symbol = symbol.upper().strip()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9.-]{0,24}\.US", symbol):
            raise ValueError("Use a US EODHD ticker, such as SPY.US")
        first, last = _day(start), _day(end)
        now = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
        if now.tzinfo is None or first > last or last.date() > now.date():
            raise ValueError("Use ordered historical dates and an aware current timestamp")
        cache_key = hashlib.sha256(f"daily-v1:{symbol}:{first}:{last}".encode()).hexdigest()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self.cache_dir / f"{cache_key}.json"
        with locked(path):
            cached = None
            if path.exists():
                try:
                    cached = json.loads(path.read_text(encoding="utf-8"))
                    age = (now - pd.Timestamp(cached["retrieved_at"])).total_seconds()
                    if not refresh and 0 <= age < self.ttl_seconds:
                        result = normalize_daily(
                            cached["rows"], first, last, cached["retrieved_at"]
                        )
                        result.metadata.update(symbol=symbol, cache_hit=True, cache_age_seconds=age)
                        result.metadata["data_age_seconds"] += age
                        return result
                except (ValueError, KeyError, TypeError):
                    cached = None
            token = os.environ.get("EODHD_API_TOKEN", "").strip()
            if not token:
                raise EODHDError("Set EODHD_API_TOKEN for EODHD downloads")
            delay = self.min_request_seconds - (time.monotonic() - self._last_request)
            if delay > 0:
                time.sleep(delay)
            self._last_request = time.monotonic()
            try:
                response = get_scrubbed(
                    f"https://eodhd.com/api/eod/{symbol}",
                    params={
                        "api_token": token,
                        "fmt": "json",
                        "period": "d",
                        "order": "a",
                        "from": first.strftime("%Y-%m-%d"),
                        "to": last.strftime("%Y-%m-%d"),
                    },
                    timeout=30,
                    secret=token,
                    passthrough=(401, 402, 403, 429),
                )
                if response.status_code in (401, 402, 403, 429):
                    raise EODHDError(
                        "EODHD authentication, entitlement or rate limit denied; "
                        "check your plan/budget before retrying"
                    )
                rows = response.json()
            except EODHDError:
                raise
            except Exception:
                raise EODHDError("EODHD request failed; no cached data was substituted") from None
            result = normalize_daily(rows, first, last, now)

            def write_snapshot(name: str) -> None:
                Path(name).write_text(
                    json.dumps({"retrieved_at": now.isoformat(), "rows": rows}), encoding="utf-8"
                )

            replace_file(path, write_snapshot)
            result.metadata.update(symbol=symbol, cache_hit=False, cache_age_seconds=0)
            return result
