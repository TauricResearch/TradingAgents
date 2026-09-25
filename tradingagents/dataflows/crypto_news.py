"""Lightweight crypto news tools using public RSS feeds."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Iterable, List, Optional

import requests

from tradingagents.dataflows.config import get_config

logger = logging.getLogger(__name__)

_FEEDS = [
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://cointelegraph.com/rss",
    "https://decrypt.co/feed",
]
_TIMEOUT = 10


def _fetch_feed(url: str) -> List[dict]:
    try:
        response = requests.get(url, timeout=_TIMEOUT, headers={"User-Agent": "TradingAgents/crypto-train"})
        response.raise_for_status()
        root = ET.fromstring(response.content)
    except Exception as exc:
        logger.warning("Crypto RSS fetch failed for %s: %s", url, exc)
        return []

    items: List[dict] = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        description = (item.findtext("description") or "").strip()
        published_raw = (item.findtext("pubDate") or "").strip()
        published = _parse_pubdate(published_raw)
        if title:
            items.append(
                {
                    "title": title,
                    "link": link,
                    "description": description,
                    "published": published,
                    "source": url,
                }
            )
    return items


def _parse_pubdate(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _matches(item: dict, query_terms: Iterable[str]) -> bool:
    text = f"{item.get('title', '')} {item.get('description', '')}".lower()
    terms = [term.lower() for term in query_terms if term]
    return not terms or any(term in text for term in terms)


def _format_items(items: List[dict], limit: int) -> str:
    if not items:
        return "No relevant crypto news found from configured public RSS feeds."
    lines = []
    for item in items[:limit]:
        published = item.get("published")
        pub_text = published.strftime("%Y-%m-%d %H:%M UTC") if published else "unknown time"
        lines.append(f"- {pub_text} | {item['title']} | {item.get('link', '')}")
    return "\n".join(lines)


def get_crypto_news(query: str, start_date: str, end_date: str) -> str:
    """Fetch recent crypto news matching a symbol or free-text query."""
    cfg = get_config()
    limit = int(cfg.get("news_article_limit", 20))
    terms = [query.replace("/USDT", ""), query.replace("USDT", ""), query]
    items: List[dict] = []
    for feed in cfg.get("crypto_news_feeds", _FEEDS):
        items.extend(item for item in _fetch_feed(feed) if _matches(item, terms))
    items.sort(key=lambda item: item.get("published") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return f"Crypto news for {query}:\n" + _format_items(items, limit)


def get_global_crypto_news(curr_date: str, look_back_days: int = 7, limit: int = 10) -> str:
    """Fetch broad crypto market headlines."""
    cfg = get_config()
    items: List[dict] = []
    for feed in cfg.get("crypto_news_feeds", _FEEDS):
        items.extend(_fetch_feed(feed))
    items.sort(key=lambda item: item.get("published") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return "Global crypto market news:\n" + _format_items(items, int(limit or cfg.get("global_news_article_limit", 10)))
