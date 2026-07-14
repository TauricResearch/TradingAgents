"""Keyless news ingestion for the sentiment agents (trader review G6).

The container pipelines never populated ``MarketSnapshot.news`` — the
NEWS_SENTIMENT team always saw an empty feed and disclosed ``news`` as
missing. This adapter pulls headlines from Yahoo Finance (keyless, the
same vendor already trusted for daily bars) and emits ``NewsItem``
contracts. Downstream stays unchanged: rendering still quarantines
instruction-attack bodies (INJ-02) and an empty/failed fetch still
degrades honestly to ``missing_feeds: ["news"]``.

``PRO_DISABLE_LIVE_VENDORS=1`` keeps tests hermetic (empty feed).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from tradingagents.contracts import NewsItem

logger = logging.getLogger(__name__)


def _parse_published(raw) -> datetime | None:
    if raw in (None, ""):
        return None
    try:
        if isinstance(raw, (int, float)):  # legacy providerPublishTime epoch
            return datetime.fromtimestamp(float(raw), tz=timezone.utc)
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (ValueError, OSError):
        return None


def _item_from_yf(raw: dict) -> NewsItem | None:
    """Normalize both yfinance news shapes (new `content` nesting and the
    legacy flat dict). Anything without a headline is dropped."""
    content = raw.get("content") if isinstance(raw.get("content"), dict) else raw
    headline = (content.get("title") or "").strip()
    if not headline:
        return None
    provider = content.get("provider")
    source = (
        (provider or {}).get("displayName")
        if isinstance(provider, dict) else content.get("publisher")
    ) or "yahoo_finance"
    url = None
    canonical = content.get("canonicalUrl")
    if isinstance(canonical, dict):
        url = canonical.get("url")
    url = url or content.get("link") or None
    summary = (content.get("summary") or content.get("description") or "").strip() or None
    published = _parse_published(
        content.get("pubDate") or raw.get("providerPublishTime")
    )
    return NewsItem(
        headline=headline,
        source=str(source),
        published_at=published,
        url=url,
        summary=summary,
    )


class YahooFinanceNewsFeed:
    """News for one ticker (e.g. ``GC=F`` for gold, ``BTC-USD``)."""

    name = "yahoo_news"

    def __init__(self, ticker: str, limit: int = 8, loader=None):
        self.ticker = ticker
        self.limit = max(1, min(limit, 25))
        self._loader = loader  # injectable for tests

    def _fetch_raw(self) -> list[dict]:
        if self._loader is not None:
            return list(self._loader(self.ticker))
        if os.environ.get("PRO_DISABLE_LIVE_VENDORS") == "1":
            return []
        import yfinance as yf

        return list(yf.Ticker(self.ticker).news or [])

    def get_news(self) -> list[NewsItem]:
        """Best-effort headlines; raises on vendor failure so the caller
        (SnapshotBuilder) can record the degradation."""
        items = []
        for raw in self._fetch_raw()[: self.limit * 2]:
            try:
                item = _item_from_yf(raw)
            except Exception:
                logger.warning("unparseable news item skipped", exc_info=True)
                continue
            if item is not None:
                items.append(item)
            if len(items) >= self.limit:
                break
        return items
