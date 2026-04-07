from __future__ import annotations

import json
from datetime import datetime, timedelta

from .alpha_vantage_common import _make_api_request, format_datetime_for_api
from .news_models import NewsItem, dedupe_news_items, format_news_items_report, normalize_datetime
from .vendor_exceptions import VendorMalformedResponseError


def _parse_news_sentiment_response(response_text: str) -> list[dict]:
    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise VendorMalformedResponseError("Alpha Vantage returned malformed NEWS_SENTIMENT payload.") from exc

    feed = payload.get("feed")
    if feed is None:
        raise VendorMalformedResponseError("Alpha Vantage NEWS_SENTIMENT payload did not include a feed.")
    if not isinstance(feed, list):
        raise VendorMalformedResponseError("Alpha Vantage NEWS_SENTIMENT feed must be a list.")
    return feed


def normalize_alpha_vantage_article(article: dict, *, fallback_symbol: str | None = None) -> NewsItem:
    raw_symbols = article.get("ticker_sentiment") or []
    symbols = [
        str(item.get("ticker", "")).upper()
        for item in raw_symbols
        if isinstance(item, dict) and str(item.get("ticker", "")).strip()
    ]
    if fallback_symbol and fallback_symbol.upper() not in symbols:
        symbols.append(fallback_symbol.upper())

    topic_tags = [
        str(item.get("topic", "")).strip()
        for item in article.get("topics", [])
        if isinstance(item, dict) and str(item.get("topic", "")).strip()
    ]

    sentiment = article.get("overall_sentiment_score")
    try:
        sentiment_value = float(sentiment) if sentiment not in (None, "") else None
    except (TypeError, ValueError):
        sentiment_value = None

    return NewsItem(
        title=str(article.get("title", "No title")),
        source=str(article.get("source", "Alpha Vantage")),
        published_at=normalize_datetime(article.get("time_published")),
        language=article.get("language"),
        country=article.get("source_domain"),
        symbols=symbols,
        topic_tags=topic_tags,
        sentiment=sentiment_value,
        relevance=None,
        reliability=None,
        url=str(article.get("url", "")),
        summary=str(article.get("summary", "")),
        raw_vendor="alpha_vantage",
    )


def fetch_company_news_alpha_vantage(ticker: str, start_date: str, end_date: str) -> list[NewsItem]:
    params = {
        "tickers": ticker,
        "time_from": format_datetime_for_api(start_date),
        "time_to": format_datetime_for_api(end_date),
        "limit": "50",
    }
    response_text = _make_api_request("NEWS_SENTIMENT", params)
    return dedupe_news_items(
        [normalize_alpha_vantage_article(article, fallback_symbol=ticker) for article in _parse_news_sentiment_response(response_text)]
    )


def get_company_news_alpha_vantage(ticker: str, start_date: str, end_date: str) -> str:
    items = fetch_company_news_alpha_vantage(ticker, start_date, end_date)
    if not items:
        return f"No news found for {ticker} between {start_date} and {end_date}"
    return format_news_items_report(
        f"{ticker} Company News, from {start_date} to {end_date}",
        items,
        max_items=25,
    )


def fetch_macro_news_alpha_vantage(
    curr_date: str,
    look_back_days: int = 7,
    limit: int = 50,
    region: str | None = None,
    language: str | None = None,
) -> list[NewsItem]:
    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_dt = curr_dt - timedelta(days=look_back_days)

    topics = "financial_markets,economy_macro,economy_monetary"
    if region and region.upper() == "KR":
        topics = "financial_markets,economy_macro"

    params = {
        "topics": topics,
        "time_from": format_datetime_for_api(start_dt.strftime("%Y-%m-%d")),
        "time_to": format_datetime_for_api(curr_date),
        "limit": str(limit),
    }
    if language:
        params["sort"] = "LATEST"

    response_text = _make_api_request("NEWS_SENTIMENT", params)
    items = [
        normalize_alpha_vantage_article(article)
        for article in _parse_news_sentiment_response(response_text)
    ]
    return dedupe_news_items(items)[:limit]


def get_macro_news_alpha_vantage(
    curr_date: str,
    look_back_days: int = 7,
    limit: int = 50,
    region: str | None = None,
    language: str | None = None,
) -> str:
    start_date = (datetime.strptime(curr_date, "%Y-%m-%d") - timedelta(days=look_back_days)).strftime("%Y-%m-%d")
    items = fetch_macro_news_alpha_vantage(
        curr_date,
        look_back_days=look_back_days,
        limit=limit,
        region=region,
        language=language,
    )
    if not items:
        return f"No global news found for {curr_date}"
    region_label = (region or "GLOBAL").upper()
    return format_news_items_report(
        f"{region_label} Macro News, from {start_date} to {curr_date}",
        items,
        max_items=limit,
    )


def get_insider_transactions(symbol: str) -> dict[str, str] | str:
    """Returns latest and historical insider transactions by key stakeholders.

    Covers transactions by founders, executives, board members, etc.

    Args:
        symbol: Ticker symbol. Example: "IBM".

    Returns:
        Dictionary containing insider transaction data or JSON string.
    """

    params = {
        "symbol": symbol,
    }

    return _make_api_request("INSIDER_TRANSACTIONS", params)


# Backward-compatible aliases
get_news = get_company_news_alpha_vantage
get_global_news = get_macro_news_alpha_vantage
