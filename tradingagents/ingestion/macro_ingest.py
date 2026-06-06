"""Macro ingestion: FRED-style series -> DB (DB-first), for the Market desk.

Macro is global (not per-ticker). The fetch is behind a protocol for offline
testing; ``FredFetcher`` is the real adapter (needs FRED_API_KEY).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, Protocol, runtime_checkable

from sqlalchemy.orm import Session

from ..storage import repository as repo

# Default macro series (FRED ids): GDP, CPI, fed funds, unemployment, 10y yield.
DEFAULT_MACRO_SERIES = ["GDP", "CPIAUCSL", "FEDFUNDS", "UNRATE", "DGS10"]


@dataclass
class MacroIngestResult:
    series_id: str
    inserted: int
    skipped: int


@runtime_checkable
class MacroFetcher(Protocol):
    def fetch(self, series_id: str, start: str, end: str) -> list[dict[str, Any]]:
        """Return observations: dicts with ``ts`` (datetime) and ``value`` (float)."""
        ...


def _naive(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


def ingest_macro(
    session: Session,
    series_id: str,
    *,
    fetcher: MacroFetcher,
    start: str = "2000-01-01",
    end: Optional[str] = None,
    vendor: Optional[str] = None,
) -> MacroIngestResult:
    end = end or datetime.now(timezone.utc).date().isoformat()
    obs = fetcher.fetch(series_id, start, end)
    if not obs:
        return MacroIngestResult(series_id, 0, 0)

    existing = {_naive(t) for t in repo.existing_macro_ts(session, series_id)}
    today = datetime.now(timezone.utc).date()
    rows: list[dict[str, Any]] = []
    for o in obs:
        ts: datetime = o["ts"]
        if _naive(ts) in existing:
            continue
        existing.add(_naive(ts))
        rows.append({
            "ts": ts,
            "value": float(o["value"]),
            "vendor": vendor or o.get("vendor"),
            "reference_date": ts.date(),
            "publication_date": today,
        })
    inserted = repo.insert_macro_points(session, series_id, rows) if rows else 0
    return MacroIngestResult(series_id, inserted, len(obs) - inserted)


class FredFetcher:
    """Real FRED adapter via the public observations API. Needs FRED_API_KEY."""

    def __init__(self, api_key: Optional[str] = None):
        import os

        self.api_key = api_key or os.environ.get("FRED_API_KEY", "")
        if not self.api_key:
            raise RuntimeError("FRED_API_KEY missing")

    def fetch(self, series_id: str, start: str, end: str) -> list[dict[str, Any]]:
        import requests

        resp = requests.get(
            "https://api.stlouisfed.org/fred/series/observations",
            params={
                "series_id": series_id,
                "api_key": self.api_key,
                "file_type": "json",
                "observation_start": start,
                "observation_end": end,
            },
            timeout=20,
        )
        resp.raise_for_status()
        out: list[dict[str, Any]] = []
        for o in resp.json().get("observations", []):
            val = o.get("value")
            if val in (None, ".", ""):
                continue
            out.append({
                "ts": datetime.strptime(o["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc),
                "value": float(val),
                "vendor": "fred",
            })
        return out
