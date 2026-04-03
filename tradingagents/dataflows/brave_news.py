from __future__ import annotations

import os
from datetime import datetime, timedelta

import requests

from .exceptions import DataVendorUnavailable


BRAVE_SEARCH_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
REQUEST_TIMEOUT = 12


def _parse_date(date_str: str) -> datetime:
    return datetime.strptime(date_str, "%Y-%m-%d")


def _get_api_key() -> str:
    api_key = os.getenv("BRAVE_SEARCH_API_KEY") or os.getenv("BRAVE_API_KEY")
    if not api_key:
        raise DataVendorUnavailable(
            "BRAVE_SEARCH_API_KEY is not set. Configure it or use fallback vendor."
        )
    return api_key


def _freshness_from_days(days: int) -> str:
    if days <= 1:
        return "pd"
    if days <= 7:
        return "pw"
    if days <= 31:
        return "pm"
    return "py"


def _search_brave(query: str, count: int, freshness: str) -> list[dict]:
    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": _get_api_key(),
    }
    params = {
        "q": query,
        "count": max(1, min(count, 20)),
        "freshness": freshness,
        "search_lang": "en",
        "country": "US",
    }

    try:
        response = requests.get(
            BRAVE_SEARCH_ENDPOINT,
            headers=headers,
            params=params,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise DataVendorUnavailable(f"Brave Search request failed: {exc}") from exc

    payload = response.json()
    return payload.get("web", {}).get("results", [])


def _format_news_block(title: str, start_date: str, end_date: str, results: list[dict]) -> str:
    if not results:
        return f"No news found for {title} between {start_date} and {end_date}."

    blocks = []
    for item in results:
        headline = item.get("title") or "No title"
        description = item.get("description") or ""
        url = item.get("url") or ""
        source = item.get("profile", {}).get("name") or "Unknown"
        age = item.get("age") or ""

        text = f"### {headline} (source: {source})"
        if age:
            text += f"\nPublished: {age}"
        if description:
            text += f"\n{description}"
        if url:
            text += f"\nLink: {url}"
        blocks.append(text)

    return f"## {title}, from {start_date} to {end_date}:\n\n" + "\n\n".join(blocks)


def get_news(ticker: str, start_date: str, end_date: str) -> str:
    start_dt = _parse_date(start_date)
    end_dt = _parse_date(end_date)
    day_window = max(1, (end_dt - start_dt).days)
    freshness = _freshness_from_days(day_window)

    query = f"{ticker} stock news earnings guidance sentiment"
    results = _search_brave(query=query, count=20, freshness=freshness)
    return _format_news_block(f"{ticker} News", start_date, end_date, results)


def get_global_news(curr_date: str, look_back_days: int = 7, limit: int = 10) -> str:
    end_dt = _parse_date(curr_date)
    start_dt = end_dt - timedelta(days=look_back_days)
    start_date = start_dt.strftime("%Y-%m-%d")

    freshness = _freshness_from_days(max(1, look_back_days))
    queries = [
        "US stock market macro news",
        "Federal Reserve rates inflation outlook",
        "global markets risk sentiment",
        "equity market volatility earnings outlook",
    ]

    merged = []
    seen_urls = set()
    per_query = max(3, min(limit, 8))

    for query in queries:
        for item in _search_brave(query=query, count=per_query, freshness=freshness):
            url = item.get("url")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            merged.append(item)
            if len(merged) >= limit:
                break
        if len(merged) >= limit:
            break

    return _format_news_block("Global Market News", start_date, curr_date, merged)
