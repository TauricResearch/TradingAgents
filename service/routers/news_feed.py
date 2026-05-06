"""Cross-ticker news aggregation.

    GET /news/feed?tickers=AAPL,MSFT&limit=50
    GET /news/feed                 -> aggregates over the watchlist by default

Pulls recent articles from yfinance for each ticker, dedupes by title,
sorts newest-first. Cached for 5 minutes per (ticker) to keep this cheap.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Query
from pydantic import BaseModel

from gui import storage
from service.streaming import _fetch_news

router = APIRouter(prefix="/news", tags=["news"])


# Per-ticker memoisation: ticker -> (timestamp, articles)
_CACHE: Dict[str, Tuple[float, List[Dict]]] = {}
_TTL = 300.0  # 5 minutes


def _cached_articles(ticker: str) -> List[Dict]:
    now = time.time()
    cached = _CACHE.get(ticker)
    if cached and now - cached[0] < _TTL:
        return cached[1]
    try:
        articles = _fetch_news(ticker)
    except Exception:
        articles = []
    _CACHE[ticker] = (now, articles)
    return articles


class NewsArticle(BaseModel):
    ticker: str
    title: str
    summary: Optional[str] = None
    publisher: Optional[str] = None
    link: Optional[str] = None
    published_at: Optional[str] = None


@router.get("/feed", response_model=List[NewsArticle])
def feed(
    tickers: Optional[str] = Query(None, description="Comma-separated; default = watchlist"),
    limit: int = Query(50, ge=1, le=500),
) -> List[NewsArticle]:
    if tickers:
        tlist = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    else:
        tlist = [w["ticker"] for w in storage.list_watchlist()]

    seen_keys = set()
    out: List[NewsArticle] = []
    for ticker in tlist:
        for a in _cached_articles(ticker):
            key = (a.get("title") or "")[:120].lower().strip()
            if not key or key in seen_keys:
                continue
            seen_keys.add(key)
            out.append(NewsArticle(ticker=ticker, **a))

    # Sort newest first by published_at when present, else lexicographic on title.
    def sort_key(n: NewsArticle):
        if n.published_at:
            try:
                return (0, datetime.fromisoformat(str(n.published_at).replace("Z", "+00:00")).timestamp())
            except Exception:
                pass
        return (1, n.title)

    out.sort(key=sort_key, reverse=True)
    return out[:limit]
