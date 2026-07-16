"""Deterministic enrichment for the FRED release calendar.

FRED knows *dates* but not times, and its ``releases/dates`` endpoint
(with ``include_release_dates_with_no_data``) lists some releases on runs
of consecutive days — the trader review caught "FOMC Press Release" as a
major event seven days straight, which is worse than no calendar at all.

This module is pure calendar hygiene, no vendor and no LLM:

- exact duplicate (release, date) rows collapse,
- a run of consecutive dates for the same release collapses to its first
  day (real releases don't repeat daily; weekly claims are 7 days apart
  and survive untouched),
- releases whose publication times are fixed by their agencies gain
  ``time_et`` and a computed ``ts_utc`` (BLS/BEA/Census publish at 08:30
  ET, the FOMC statement at 14:00 ET — stable for decades). Releases
  without a known time keep honest nulls; the UI says "time unknown"
  rather than guessing.

Consensus/forecast figures require a licensed vendor and are deliberately
absent — nothing here fabricates a number.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")

# publication times fixed by the issuing agency (ET). Patterns match the
# FRED release names already flowing through the calendar.
_RELEASE_TIMES_ET: tuple[tuple[re.Pattern[str], tuple[int, int]], ...] = (
    (re.compile(r"fomc", re.IGNORECASE), (14, 0)),
    (re.compile(
        r"consumer price index|employment situation|producer price index|"
        r"gross domestic product|advance monthly sales|retail sales|"
        r"personal income and outlays|unemployment insurance weekly claims",
        re.IGNORECASE), (8, 30)),
    (re.compile(r"university of michigan|ism report|jolts", re.IGNORECASE),
     (10, 0)),
)


def _time_et_for(release: str) -> tuple[int, int] | None:
    for pattern, hm in _RELEASE_TIMES_ET:
        if pattern.search(release):
            return hm
    return None


def enrich_calendar(releases: list[dict]) -> list[dict]:
    """Dedupe, collapse consecutive-day runs, and attach known times.

    Input rows are the FRED fetcher's ``{date, release, release_id, major}``
    dicts; output preserves that shape and adds ``time_et`` ("HH:MM" ET or
    None) and ``ts_utc`` (ISO instant or None). Order: by date, majors
    first within a date.
    """
    # exact dedupe, keeping first occurrence
    seen: set[tuple[str, str]] = set()
    rows: list[dict] = []
    for row in releases:
        key = (str(row.get("release", "")), str(row.get("date", "")))
        if key in seen:
            continue
        seen.add(key)
        rows.append(dict(row))

    # collapse consecutive-day runs per release: a real release happens
    # once; N-days-in-a-row is a FRED realtime artifact (review P1.1)
    by_release: dict[str, list[dict]] = {}
    for row in rows:
        by_release.setdefault(str(row.get("release", "")), []).append(row)
    kept: list[dict] = []
    for group in by_release.values():
        group.sort(key=lambda r: str(r.get("date", "")))
        prev: date | None = None
        for row in group:
            try:
                day = date.fromisoformat(str(row.get("date", "")))
            except ValueError:
                kept.append(row)
                prev = None
                continue
            if prev is not None and (day - prev) == timedelta(days=1):
                prev = day  # extend the run; drop the row
                continue
            prev = day
            kept.append(row)

    for row in kept:
        hm = _time_et_for(str(row.get("release", "")))
        if hm is None:
            row["time_et"] = None
            row["ts_utc"] = None
            continue
        row["time_et"] = f"{hm[0]:02d}:{hm[1]:02d}"
        try:
            day = date.fromisoformat(str(row.get("date", "")))
            instant = datetime(day.year, day.month, day.day, *hm, tzinfo=_ET)
            row["ts_utc"] = instant.astimezone(ZoneInfo("UTC")).isoformat()
        except ValueError:
            row["ts_utc"] = None

    kept.sort(key=lambda r: (str(r.get("date", "")), not r.get("major", False)))
    return kept


def next_major_event(releases: list[dict], now: datetime) -> dict | None:
    """The nearest upcoming major event with a known instant — the input to
    countdown chips and the pipeline's event gate. Events without a known
    time count from end-of-day ET (conservative: still upcoming)."""
    best: tuple[datetime, dict] | None = None
    for row in releases:
        if not row.get("major"):
            continue
        ts = row.get("ts_utc")
        if ts:
            try:
                instant = datetime.fromisoformat(ts)
            except ValueError:
                continue
        else:
            try:
                day = date.fromisoformat(str(row.get("date", "")))
            except ValueError:
                continue
            instant = datetime(day.year, day.month, day.day, 23, 59,
                               tzinfo=_ET).astimezone(ZoneInfo("UTC"))
        if instant <= now:
            continue
        if best is None or instant < best[0]:
            best = (instant, row)
    if best is None:
        return None
    return {**best[1], "at": best[0].isoformat(),
            "seconds_until": int((best[0] - now).total_seconds())}
