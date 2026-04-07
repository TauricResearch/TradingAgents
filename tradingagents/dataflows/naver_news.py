from __future__ import annotations

import html
import re
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

import requests

from tradingagents.agents.utils.instrument_resolver import resolve_instrument

from .api_keys import get_api_key
from .config import get_config
from .news_models import NewsItem, dedupe_news_items, filter_news_items_by_date, format_news_items_report
from .vendor_exceptions import VendorConfigurationError, VendorMalformedResponseError, VendorTransientError


_NAVER_NEWS_ENDPOINT = "https://openapi.naver.com/v1/search/news.json"


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", html.unescape(text or "")).strip()


def _get_headers() -> dict[str, str]:
    client_id = get_api_key("NAVER_CLIENT_ID")
    client_secret = get_api_key("NAVER_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise VendorConfigurationError("Naver News credentials are not configured.")
    return {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    }


def normalize_naver_article(article: dict, *, fallback_symbol: str) -> NewsItem:
    published_at = None
    if article.get("pubDate"):
        try:
            published_at = parsedate_to_datetime(article["pubDate"])
        except (TypeError, ValueError, IndexError):
            published_at = None
    return NewsItem(
        title=_strip_html(article.get("title", "No title")),
        source="Naver News",
        published_at=published_at,
        language="ko",
        country="KR",
        symbols=[fallback_symbol.upper()],
        topic_tags=[],
        sentiment=None,
        relevance=None,
        reliability=None,
        url=article.get("originallink") or article.get("link") or "",
        summary=_strip_html(article.get("description", "")),
        raw_vendor="naver",
    )


def fetch_company_news_naver(symbol: str, start_date: str, end_date: str, display: int = 20) -> list[NewsItem]:
    profile = resolve_instrument(symbol)
    search_query = profile.display_name if profile.country == "KR" else symbol
    try:
        response = requests.get(
            _NAVER_NEWS_ENDPOINT,
            headers=_get_headers(),
            params={"query": search_query, "display": display, "sort": "date"},
            timeout=float(get_config().get("vendor_timeout", 15)),
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise VendorTransientError(f"Naver News request failed: {exc}") from exc

    payload = response.json()
    items = payload.get("items")
    if not isinstance(items, list):
        raise VendorMalformedResponseError("Naver News payload did not include an items list.")

    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
    normalized = dedupe_news_items(
        [normalize_naver_article(article, fallback_symbol=profile.primary_symbol) for article in items]
    )
    return filter_news_items_by_date(normalized, start_date=start_dt, end_date=end_dt)


def get_company_news_naver(symbol: str, start_date: str, end_date: str) -> str:
    items = fetch_company_news_naver(symbol, start_date, end_date)
    if not items:
        return f"No news found for {symbol} between {start_date} and {end_date}"
    return format_news_items_report(
        f"{symbol} Company News, from {start_date} to {end_date}",
        items,
        max_items=15,
    )


def get_social_sentiment_naver(symbol: str, start_date: str, end_date: str) -> str:
    items = fetch_company_news_naver(symbol, start_date, end_date, display=10)
    if not items:
        return (
            f"Dedicated social provider unavailable; Naver company-news sentiment was unavailable for {symbol} "
            f"between {start_date} and {end_date}."
        )
    lines = [
        f"Dedicated social provider unavailable; using Korean news-derived public narrative for {symbol} from {start_date} to {end_date}.",
        "",
    ]
    for item in items[:10]:
        stamp = item.published_at.strftime("%Y-%m-%d") if item.published_at else "undated"
        lines.append(f"- {stamp}: {item.title}")
        if item.summary:
            lines.append(f"  Narrative: {item.summary}")
    return "\n".join(lines)
