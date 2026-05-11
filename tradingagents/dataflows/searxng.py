"""SearXNG-based news data fetching functions.

SearXNG is a self-hosted, privacy-respecting metasearch engine that aggregates
results from 70+ search engines (Google, Bing, DuckDuckGo, Reddit, Yahoo, ...).
Because SearXNG is local and unauthenticated, it lets the news/sentiment
analysts cover sources that would otherwise require paid APIs.

Set SEARXNG_BASE_URL to point at the JSON-API endpoint
(default ``http://localhost:8888``).
"""

import os
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Iterable, List, Optional

import requests
import yfinance as yf

DEFAULT_BASE_URL = "http://localhost:8888"
REQUEST_TIMEOUT_SECONDS = 15


class SearxngUnavailableError(Exception):
    """Raised when the configured SearXNG instance cannot be reached.

    Triggers fallback to the next vendor in the chain (see ``route_to_vendor``).
    """


def _base_url() -> str:
    return os.getenv("SEARXNG_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


@lru_cache(maxsize=128)
def _company_name(ticker: str) -> Optional[str]:
    """Resolve a ticker to its company name via yfinance ``.info``.

    Cached because company names are static for a ticker and the underlying
    ``yfinance.Ticker.info`` lookup makes a blocking network call. Returns
    ``None`` if the lookup fails so callers can fall back to the raw ticker
    without aborting the search.
    """
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception:
        return None
    for key in ("longName", "shortName", "displayName"):
        name = info.get(key)
        if name:
            return name
    return None


def _ticker_queries(ticker: str) -> List[str]:
    """Build a small set of queries covering different facets of a ticker.

    The fourth query is the one that gives the Social Media Analyst real
    sentiment data — it pulls posts directly from Reddit and X/Twitter.
    """
    company = _company_name(ticker) or ticker
    return [
        f"{ticker} stock news",
        f"{company} earnings revenue",
        f"{ticker} analyst upgrade downgrade",
        f"{ticker} site:reddit.com OR site:x.com",
    ]


def _search(query: str, time_range: Optional[str] = None) -> List[dict]:
    """Call the SearXNG JSON API once.

    Raises:
        SearxngUnavailableError: If the instance is unreachable or replies
        with a non-success status. Network-level failures here are what the
        vendor router uses to fall back to the next configured vendor.
    """
    params = {"q": query, "format": "json", "categories": "news,general"}
    if time_range:
        params["time_range"] = time_range
    try:
        response = requests.get(
            f"{_base_url()}/search",
            params=params,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json().get("results", []) or []
    except (requests.RequestException, ValueError) as exc:
        raise SearxngUnavailableError(f"SearXNG request failed: {exc}") from exc


def _parse_published(value) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except (ValueError, AttributeError):
        return None


def _dedupe_and_filter(
    results: Iterable[dict],
    start: Optional[datetime],
    end: Optional[datetime],
) -> List[dict]:
    """Drop duplicates and results published outside the date window.

    Results without a parseable publish date are kept — SearXNG engines vary
    in what metadata they expose, and dropping them would silently discard
    most of the social-media corpus.
    """
    seen: set = set()
    kept: List[dict] = []
    for result in results:
        url = (result.get("url") or "").strip()
        title = (result.get("title") or "").strip()
        key = url or title
        if not key or key in seen:
            continue
        if start is not None and end is not None:
            published = _parse_published(result.get("publishedDate"))
            if published is not None and not (start <= published <= end + timedelta(days=1)):
                continue
        seen.add(key)
        kept.append(result)
    return kept


def _format_results(results: Iterable[dict]) -> str:
    lines: List[str] = []
    for result in results:
        title = result.get("title") or "Untitled"
        publisher = result.get("engine") or "SearXNG"
        url = result.get("url") or ""
        snippet = result.get("content") or ""
        lines.append(f"### {title} (source: {publisher})")
        if snippet:
            lines.append(snippet)
        if url:
            lines.append(f"Link: {url}")
        lines.append("")
    return "\n".join(lines)


def get_news_searxng(
    ticker: str,
    start_date: str,
    end_date: str,
    limit: int = 20,
) -> str:
    """Retrieve news for a ticker via SearXNG.

    Returns a markdown-formatted string matching the yfinance vendor's shape so
    downstream agents can consume either vendor interchangeably. ``limit``
    caps the total number of articles emitted to keep the output within the
    LLM's context window — four facet queries can otherwise return ~40 hits.
    """
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    aggregated: List[dict] = []
    for query in _ticker_queries(ticker):
        aggregated.extend(_search(query, time_range="month"))

    filtered = _dedupe_and_filter(aggregated, start_dt, end_dt)[:limit]
    if not filtered:
        return f"No news found for {ticker} between {start_date} and {end_date}"

    return f"## {ticker} News, from {start_date} to {end_date}:\n\n{_format_results(filtered)}"


def get_global_news_searxng(
    curr_date: str,
    look_back_days: int = 7,
    limit: int = 10,
) -> str:
    """Retrieve macro/global news via SearXNG."""
    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_dt = curr_dt - timedelta(days=look_back_days)
    queries = [
        "stock market economy",
        "Federal Reserve interest rates",
        "inflation economic outlook",
        "global markets trading",
    ]

    aggregated: List[dict] = []
    for query in queries:
        aggregated.extend(_search(query, time_range="week"))
        if len(aggregated) >= limit * 4:
            break

    filtered = _dedupe_and_filter(aggregated, start_dt, curr_dt)[:limit]
    if not filtered:
        return f"No global news found for {curr_date}"

    return (
        f"## Global Market News, from {start_dt.strftime('%Y-%m-%d')} to {curr_date}:\n\n"
        f"{_format_results(filtered)}"
    )
