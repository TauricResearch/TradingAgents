"""Yfinance-backed historical price bars for the dashboard's chart feature.

Wraps ``yf.Ticker.history`` with an in-memory TTL cache and exposes
range resolution (preset → start/end/interval). The HTTP layer in
:mod:`web.server.app` is a thin adapter around :func:`get_history`.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

import yfinance as yf

from web.server import queries, storage as _storage

log = logging.getLogger(__name__)


#: Window size for each preset. "all" is the 1y cap per the spec.
_PRESET_WINDOWS: dict[str, timedelta] = {
    "1d": timedelta(days=1),
    "5d": timedelta(days=5),
    "1mo": timedelta(days=30),
    "3mo": timedelta(days=90),
    "6mo": timedelta(days=180),
    "1y": timedelta(days=365),
    "all": timedelta(days=365),
}


def now_utc() -> datetime:
    """Pluggable clock for tests."""
    return datetime.now(timezone.utc)


def resolve_range(
    preset: str,
    *,
    earliest_started_at: datetime | None,
) -> tuple[datetime, datetime, str]:
    """Translate a user preset into a concrete (start, end, interval).

    Args:
        preset: One of ``{1d, 5d, 1mo, 3mo, 6mo, 1y, all, auto}``.
        earliest_started_at: The earliest run's ``started_at`` for
            ``preset="auto"``. ``None`` for all other presets. Required
            for ``auto`` — the function raises :class:`ValueError` if
            missing.

    Returns:
        ``(start, end, interval)`` where ``interval`` is one of
        ``{"1m", "1h", "1d"}`` chosen by the span between start and end.

    Raises:
        ValueError: on an unknown preset, or on ``auto`` with no runs.
    """
    if preset == "auto":
        if earliest_started_at is None:
            raise ValueError("auto preset requires earliest_started_at (no runs)")
        start = earliest_started_at
        end = now_utc()
    else:
        if preset not in _PRESET_WINDOWS:
            raise ValueError(f"invalid preset: {preset!r}")
        end = now_utc()
        start = end - _PRESET_WINDOWS[preset]

    interval = _interval_for_span(end - start)
    return start, end, interval


def _interval_for_span(span: timedelta) -> str:
    """Pick the yfinance interval that fits the span without oversampling.

    ≤ 7d → 1m   (highest resolution; 1m is fresh for 7 days)
    ≤ 60d → 1h  (1m caps at 7d; 1h caps at 730d)
    > 60d → 1d  (1h is wasteful; 1d is fine for multi-month views)
    """
    if span <= timedelta(days=7):
        return "1m"
    if span <= timedelta(days=60):
        return "1h"
    return "1d"


# ---- cache ----

#: Key ``(ticker_upper, interval, start.date(), end.date())``.
#: Value ``(fetched_at_monotonic, bars)``.
_bar_cache: dict[tuple[str, str, object, object], tuple[float, list[dict]]] = {}

#: TTL by interval. 1m polls are short; 1d polls are long.
_CACHE_TTL_S: dict[str, int] = {
    "1m": 60,
    "1h": 300,
    "1d": 3600,
}


def fetch_history_bars(
    ticker: str,
    *,
    start: datetime | None,
    end: datetime | None,
    interval: str,
) -> list[dict]:
    """Return OHLCV bars for ``ticker`` between ``start`` and ``end``.

    Caches the result in process memory keyed by
    ``(ticker, interval, start.date(), end.date())`` with a TTL that
    depends on the interval. ``start``/``end`` are resolved by the
    caller (typically :func:`resolve_range`); passing ``None`` is
    allowed but uses epoch / now as the implicit bounds, which usually
    is not what you want.

    Returns a list of ``Bar`` dicts (the JSON shape the API serialises).
    An empty DataFrame yields ``[]`` (not an error).
    """
    if end is None:
        end = now_utc()
    if start is None:
        start = end - timedelta(days=365)

    key = (ticker.upper(), interval, start.date(), end.date())
    now_mono = time.monotonic()
    ttl = _CACHE_TTL_S.get(interval, 60)
    cached = _bar_cache.get(key)
    if cached is not None:
        fetched_at, bars = cached
        if now_mono - fetched_at < ttl:
            return bars

    df = yf.Ticker(ticker.upper()).history(
        start=start, end=end, interval=interval, auto_adjust=False,
    )
    bars = _df_to_bars(df)
    _bar_cache[key] = (now_mono, bars)
    return bars


def _df_to_bars(df) -> list[dict]:
    """Convert a yfinance DataFrame to the API's Bar JSON shape.

    Empty DataFrame → []. Index is normalised to UTC; rows are returned
    in index order (ascending). The Volume column is read if present;
    the spec tolerates it being absent.
    """
    if df is None or len(df) == 0:
        return []
    idx = df.index
    if hasattr(idx, "tz") and idx.tz is not None:
        idx = idx.tz_convert("UTC")
    elif hasattr(idx, "tz_localize"):
        idx = idx.tz_localize("UTC")
    ts_iso = [t.isoformat().replace("+00:00", "Z") for t in idx]
    volumes = df["Volume"].tolist() if "Volume" in df.columns else [0.0] * len(df)
    return [
        {"t": t, "o": float(o), "h": float(h), "l": float(low_val), "c": float(c), "v": float(v)}
        for t, o, h, low_val, c, v in zip(
            ts_iso, df["Open"].tolist(), df["High"].tolist(),
            df["Low"].tolist(), df["Close"].tolist(), volumes,
            strict=True,
        )
    ]


def get_history(ticker: str, preset: str) -> tuple[int, object]:
    """Orchestrator: resolve the range, fetch bars, and load runs.

    Returns ``(status_code, body)`` where ``body`` is either an error
    envelope ``{"error": str, "detail": str}`` (status 404/422/502) or
    the success body from the spec's API section.

    Does not raise — converts yfinance failures and bad input into
    structured responses so the FastAPI layer can forward them.
    """
    safe = ticker.upper()

    # 1. Load runs. A ticker with zero completed runs → 404.
    rows = _storage.list_ticker_runs(safe, limit=500)
    if not rows:
        return 404, {"error": "no_runs", "detail": f"{safe} has no completed runs"}

    # 2. Resolve the range. Unknown preset → 422.
    earliest = None
    for r in rows:
        s = r.get("started_at")
        if not s:
            continue
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            continue
        if earliest is None or dt < earliest:
            earliest = dt
    try:
        start, end, interval = resolve_range(preset, earliest_started_at=earliest)
    except ValueError as exc:
        return 422, {"error": "invalid_range", "detail": str(exc)}

    # 3. Fetch bars. yfinance failures → 502.
    try:
        bars = fetch_history_bars(safe, start=start, end=end, interval=interval)
    except Exception as exc:  # noqa: BLE001 — yfinance raises a zoo of types
        log.warning("yfinance failed for %s: %s", safe, exc)
        return 502, {"error": "yfinance_failed", "detail": str(exc)}

    # 4. Shape runs for the response. Use the existing helper so the
    #    shape matches GET /api/runs/{id} (events, llm_calls, stages).
    runs_out = [queries.run_to_dict(r) for r in rows]

    body = {
        "ticker": safe,
        "range": preset,
        "range_start": start.isoformat().replace("+00:00", "Z"),
        "range_end": end.isoformat().replace("+00:00", "Z"),
        "resolution": interval,
        "bars": bars,
        "runs": runs_out,
    }
    return 200, body
