"""News ingestion: vendor -> DB (DB-first dedup, write-through).

Feeds the Market (catalysts) and Sentiment (tone) desks. Like price ingestion,
the fetch is behind a protocol so it is testable offline; ``YFinanceNewsFetcher``
is a real adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, Protocol, runtime_checkable

from sqlalchemy.orm import Session

from ..storage import repository as repo


@dataclass
class NewsIngestResult:
    symbol: str
    inserted: int
    skipped: int


@runtime_checkable
class NewsFetcher(Protocol):
    def fetch(self, symbol: str) -> list[dict[str, Any]]:
        """Return news items: dicts with ``headline`` + ``ts`` (datetime) at least."""
        ...


def _dedup_key(item: dict[str, Any]) -> str:
    url = item.get("url")
    if url:
        return str(url)
    ts = item.get("ts")
    return f"{item.get('headline', '')}|{ts.isoformat() if isinstance(ts, datetime) else ts}"


def ingest_news(
    session: Session, symbol: str, *, fetcher: NewsFetcher, vendor: Optional[str] = None
) -> NewsIngestResult:
    items = fetcher.fetch(symbol)
    if not items:
        return NewsIngestResult(symbol, 0, 0)

    existing = repo.existing_news_keys(session, symbol)
    today = datetime.now(timezone.utc).date()
    rows: list[dict[str, Any]] = []
    for it in items:
        key = _dedup_key(it)
        if key in existing:
            continue
        existing.add(key)
        ts: datetime = it["ts"]
        rows.append(
            {
                "ts": ts,
                "headline": it["headline"],
                "summary": it.get("summary"),
                "source": it.get("source"),
                "url": it.get("url"),
                "sentiment": it.get("sentiment"),
                "dedup_key": key,
                "vendor": vendor or it.get("vendor"),
                "reference_date": ts.date() if isinstance(ts, datetime) else None,
                "publication_date": today,
            }
        )
    inserted = repo.insert_news_items(session, symbol, rows) if rows else 0
    return NewsIngestResult(symbol, inserted, len(items) - inserted)


class YFinanceNewsFetcher:
    """Real adapter over yfinance .news. Network-bound (integration)."""

    def fetch(self, symbol: str) -> list[dict[str, Any]]:
        import yfinance as yf

        raw = getattr(yf.Ticker(symbol.upper()), "news", None) or []
        items: list[dict[str, Any]] = []
        for n in raw:
            content = n.get("content", n)  # newer yfinance nests under 'content'
            title = content.get("title") or n.get("title")
            if not title:
                continue
            epoch = n.get("providerPublishTime")
            ts = (
                datetime.fromtimestamp(epoch, tz=timezone.utc)
                if epoch
                else datetime.now(timezone.utc)
            )
            items.append(
                {
                    "ts": ts,
                    "headline": title,
                    "summary": content.get("summary"),
                    "source": (n.get("publisher") or (content.get("provider") or {}).get("displayName")),
                    "url": n.get("link") or (content.get("canonicalUrl") or {}).get("url"),
                    "vendor": "yfinance",
                }
            )
        return items
