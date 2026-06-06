"""Social-sentiment ingestion: forums/social -> DB (DB-first), for the Sentiment desk.

StockTwits exposes a keyless public stream, so ``StockTwitsFetcher`` is a real
adapter usable without credentials. The fetch is behind a protocol for offline
testing. Reddit/X can be added behind the same protocol later.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, Protocol, runtime_checkable

from sqlalchemy.orm import Session

from ..storage import repository as repo


@dataclass
class SocialIngestResult:
    symbol: str
    inserted: int
    skipped: int


@runtime_checkable
class SocialFetcher(Protocol):
    def fetch(self, symbol: str) -> list[dict[str, Any]]:
        """Return posts: dicts with ``ts`` (datetime), ``body`` and ``platform``."""
        ...


def _dedup_key(item: dict[str, Any]) -> str:
    if item.get("id") is not None:
        return f"{item.get('platform', '')}:{item['id']}"
    ts = item.get("ts")
    return f"{item.get('platform','')}|{item.get('body','')[:80]}|{ts}"


def ingest_social(session: Session, symbol: str, *, fetcher: SocialFetcher) -> SocialIngestResult:
    items = fetcher.fetch(symbol)
    if not items:
        return SocialIngestResult(symbol, 0, 0)

    existing = repo.existing_social_keys(session, symbol)
    today = datetime.now(timezone.utc).date()
    rows: list[dict[str, Any]] = []
    for it in items:
        key = _dedup_key(it)
        if key in existing:
            continue
        existing.add(key)
        ts: datetime = it["ts"]
        rows.append({
            "ts": ts,
            "platform": it.get("platform", "unknown"),
            "body": it["body"],
            "sentiment": it.get("sentiment"),
            "url": it.get("url"),
            "dedup_key": key,
            "reference_date": ts.date() if isinstance(ts, datetime) else None,
            "publication_date": today,
        })
    inserted = repo.insert_social_posts(session, symbol, rows) if rows else 0
    return SocialIngestResult(symbol, inserted, len(items) - inserted)


_SENTIMENT_MAP = {"Bullish": 1.0, "Bearish": -1.0}


class StockTwitsFetcher:
    """Real, keyless adapter over the StockTwits public symbol stream."""

    def fetch(self, symbol: str) -> list[dict[str, Any]]:
        import requests

        resp = requests.get(
            f"https://api.stocktwits.com/api/2/streams/symbol/{symbol.upper()}.json",
            timeout=15,
        )
        if resp.status_code != 200:
            return []
        out: list[dict[str, Any]] = []
        for m in resp.json().get("messages", []):
            created = m.get("created_at")
            try:
                ts = datetime.strptime(created, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            except (TypeError, ValueError):
                ts = datetime.now(timezone.utc)
            basic = ((m.get("entities") or {}).get("sentiment") or {}).get("basic")
            out.append({
                "id": m.get("id"),
                "ts": ts,
                "platform": "stocktwits",
                "body": m.get("body", ""),
                "sentiment": _SENTIMENT_MAP.get(basic),
            })
        return out
