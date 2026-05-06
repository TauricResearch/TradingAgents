"""Crypto news aggregation via RSS.

Pulls headlines from a curated set of reputable crypto financial news
sites. RSS is free, requires no API keys, and gives us reasonably timely
coverage. The News Analyst (Phase 2) reads this module's markdown output
to build its narrative.
"""

from __future__ import annotations

import datetime as _dt
import logging
from typing import Dict, List, Optional

import feedparser

from ._cache import cached_json

logger = logging.getLogger(__name__)


# Curated feeds. Order matters — earlier feeds are surfaced first when
# we trim to ``limit`` articles. Each feed entry: (label, url).
DEFAULT_FEEDS: List[tuple] = [
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("CoinTelegraph", "https://cointelegraph.com/rss"),
    ("The Block", "https://www.theblock.co/rss.xml"),
    ("Decrypt", "https://decrypt.co/feed"),
    ("Bitcoin Magazine", "https://bitcoinmagazine.com/feed"),
]


def _parse_feed(url: str) -> Optional[Dict]:
    def _fetch():
        d = feedparser.parse(url)
        if d.bozo and not d.entries:
            return None
        return {
            "entries": [
                {
                    "title": e.get("title", "").strip(),
                    "link": e.get("link", ""),
                    "summary": (e.get("summary") or "").strip(),
                    "published": e.get("published") or e.get("updated") or "",
                }
                for e in d.entries[:25]
            ]
        }

    key = "rss_" + url.replace("/", "_").replace(":", "")[:80]
    return cached_json(key, ttl_seconds=600, fetcher=_fetch)


def _within_window(published: str, since: _dt.datetime) -> bool:
    if not published:
        return True  # default to including, rather than dropping unparseable dates
    for fmt in (
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
    ):
        try:
            parsed = _dt.datetime.strptime(published, fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=_dt.timezone.utc)
            return parsed >= since
        except ValueError:
            continue
    return True


def fetch_headlines(
    query: str | None = None,
    look_back_days: int = 3,
    limit: int = 15,
    feeds: List[tuple] | None = None,
) -> List[Dict]:
    """Aggregate recent crypto headlines across the configured RSS feeds.

    Args:
        query: optional substring to filter titles + summaries (case-insensitive).
        look_back_days: drop articles older than this window.
        limit: cap on returned articles (most-recent-first across feeds).
        feeds: optional override of the (label, url) feed list.
    """
    feeds = feeds or DEFAULT_FEEDS
    since = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=look_back_days)
    needle = query.lower().strip() if query else None

    collected: List[Dict] = []
    for label, url in feeds:
        feed = _parse_feed(url)
        if not feed:
            continue
        for entry in feed.get("entries", []):
            if not _within_window(entry.get("published", ""), since):
                continue
            if needle:
                hay = (entry.get("title", "") + " " + entry.get("summary", "")).lower()
                if needle not in hay:
                    continue
            collected.append({**entry, "source": label})

    # Stable sort by published-date descending; entries without a usable
    # date go to the end.
    def _ts(item):
        for fmt in (
            "%a, %d %b %Y %H:%M:%S %z",
            "%a, %d %b %Y %H:%M:%S %Z",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%SZ",
        ):
            try:
                p = _dt.datetime.strptime(item.get("published", ""), fmt)
                if p.tzinfo is None:
                    p = p.replace(tzinfo=_dt.timezone.utc)
                return p
            except ValueError:
                continue
        return _dt.datetime.min.replace(tzinfo=_dt.timezone.utc)

    collected.sort(key=_ts, reverse=True)
    return collected[:limit]


def render_headlines_markdown(headlines: List[Dict]) -> str:
    if not headlines:
        return "No recent crypto headlines matched the query/window."
    lines = []
    for h in headlines:
        published = h.get("published") or "—"
        lines.append(
            f"- **{h.get('source', '?')} · {published[:25]}** — "
            f"[{h.get('title', '')}]({h.get('link', '')})"
        )
        summary = (h.get("summary") or "").strip()
        if summary and len(summary) < 280:
            lines.append(f"  {summary}")
    return "\n".join(lines)
