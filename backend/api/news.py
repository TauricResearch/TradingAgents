"""Live news feed endpoint — uses yfinance, short-lived in-memory cache."""
import logging
import time
from fastapi import APIRouter, Depends, Query
from backend.api.deps import get_current_user

router = APIRouter(prefix="/api/news", tags=["news"])
_logger = logging.getLogger(__name__)

_CACHE: dict[str, tuple[float, list]] = {}  # ticker → (ts, items)
_TTL = 900  # 15 minutes


def _fetch_news(ticker: str, limit: int) -> list[dict]:
    import yfinance as yf
    now = time.time()
    if ticker in _CACHE and now - _CACHE[ticker][0] < _TTL:
        return _CACHE[ticker][1][:limit]
    try:
        items = yf.Ticker(ticker).news or []
        parsed = []
        for n in items[:30]:
            content = n.get("content", {})
            title = content.get("title") or n.get("title", "")
            summary = content.get("summary") or n.get("summary", "")
            url = (content.get("canonicalUrl") or {}).get("url") or n.get("link", "")
            pub = content.get("pubDate") or n.get("providerPublishTime", "")
            provider = (content.get("provider") or {}).get("displayName") or n.get("publisher", "")
            if title:
                parsed.append({"ticker": ticker, "title": title, "summary": summary,
                               "url": url, "published_at": str(pub), "source": provider})
        _CACHE[ticker] = (now, parsed)
        return parsed[:limit]
    except Exception as exc:
        _logger.debug("News fetch failed %s: %s", ticker, exc)
        return []


@router.get("/feed")
async def get_news_feed(
    tickers: str = Query(..., description="Comma-separated ticker list, e.g. AAPL,TSLA"),
    limit: int = Query(default=5, ge=1, le=20),
    _=Depends(get_current_user),
):
    """Return recent news for each ticker, merged and sorted by date."""
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()][:10]
    all_news: list[dict] = []
    for t in ticker_list:
        all_news.extend(_fetch_news(t, limit))
    all_news.sort(key=lambda x: x.get("published_at", ""), reverse=True)
    return all_news[:limit * len(ticker_list)]
