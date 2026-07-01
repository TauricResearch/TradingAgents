"""Exa neural search vendor for news data.

Exa (https://exa.ai) is a neural/semantic search engine over the live web,
useful as a news_data vendor alongside yfinance and Alpha Vantage — it is not
tied to a single publisher's feed and tends to surface longer-tail sources.

Uses Exa's REST API (https://docs.exa.ai) directly via ``requests``, like the
other vendors in this package, rather than the ``exa_py`` SDK. A free API key
(https://dashboard.exa.ai/api-keys) is read from ``EXA_API_KEY``; if it is
unset the vendor raises ``ExaNotConfiguredError`` so the routing layer treats
it as "unavailable" rather than a hard crash.
"""
import logging
import os
from datetime import datetime

import requests
from dateutil.relativedelta import relativedelta

from .errors import VendorNotConfiguredError

logger = logging.getLogger(__name__)

EXA_API_BASE = "https://api.exa.ai"

# Network timeout (seconds), consistent with the other vendors.
REQUEST_TIMEOUT = 30

# Exa charges per result; cap generously above the config defaults so a
# caller-supplied limit is always satisfiable without over-fetching.
MAX_RESULTS = 25


class ExaNotConfiguredError(VendorNotConfiguredError):
    """Raised when Exa is selected but no API key is configured.

    A VendorNotConfiguredError (and thus still a ValueError), so the routing
    layer's "vendor unavailable" handling and existing ValueError callers both
    keep working.
    """


def get_api_key() -> str:
    """Retrieve the Exa API key from the environment."""
    api_key = os.getenv("EXA_API_KEY")
    if not api_key:
        raise ExaNotConfiguredError(
            "EXA_API_KEY environment variable is not set. Get a free key at "
            "https://dashboard.exa.ai/api-keys."
        )
    return api_key


def _search(payload: dict) -> list[dict]:
    """POST to Exa's /search endpoint and return the ``results`` list."""
    response = requests.post(
        f"{EXA_API_BASE}/search",
        headers={"x-api-key": get_api_key(), "Content-Type": "application/json"},
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json().get("results", [])


def _format_results(results: list[dict]) -> str:
    parts = []
    for item in results:
        title = item.get("title") or "No title"
        publisher = item.get("author") or (item.get("url", "").split("/")[2] if item.get("url") else "Unknown")
        published = item.get("publishedDate", "")
        summary = (item.get("summary") or item.get("text") or "").strip()
        url = item.get("url", "")

        parts.append(f"### {title} (source: {publisher}{f', {published[:10]}' if published else ''})")
        if summary:
            parts.append(summary[:1000])
        if url:
            parts.append(f"Link: {url}")
        parts.append("")
    return "\n".join(parts)


def get_news_exa(
    ticker: str,
    start_date: str,
    end_date: str,
) -> str:
    """
    Retrieve news for a specific stock ticker using Exa neural search.

    Args:
        ticker: Stock ticker symbol (e.g., "AAPL")
        start_date: Start date in yyyy-mm-dd format
        end_date: End date in yyyy-mm-dd format

    Returns:
        Formatted string containing news articles
    """
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    results = _search({
        "query": f"{ticker} stock news",
        "type": "auto",
        "category": "news",
        "numResults": MAX_RESULTS,
        "startPublishedDate": f"{start_date}T00:00:00.000Z",
        "endPublishedDate": f"{(end_dt + relativedelta(days=1)).strftime('%Y-%m-%d')}T00:00:00.000Z",
        "contents": {"summary": True},
    })

    if not results:
        return f"No news found for {ticker} between {start_date} and {end_date}"

    return f"## {ticker} News, from {start_date} to {end_date}:\n\n{_format_results(results)}"


def get_global_news_exa(
    curr_date: str,
    look_back_days: int | None = None,
    limit: int | None = None,
) -> str:
    """
    Retrieve global/macro economic news using Exa neural search.

    Args:
        curr_date: Current date in yyyy-mm-dd format
        look_back_days: Number of days to look back. ``None`` falls back to 7.
        limit: Maximum number of articles to return. ``None`` falls back to 10.

    Returns:
        Formatted string containing global news articles
    """
    if look_back_days is None:
        look_back_days = 7
    if limit is None:
        limit = 10

    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_dt = curr_dt - relativedelta(days=look_back_days)
    start_date = start_dt.strftime("%Y-%m-%d")

    results = _search({
        "query": "macroeconomic and financial market news",
        "type": "auto",
        "category": "news",
        "numResults": min(limit, MAX_RESULTS),
        "startPublishedDate": f"{start_date}T00:00:00.000Z",
        "endPublishedDate": f"{(curr_dt + relativedelta(days=1)).strftime('%Y-%m-%d')}T00:00:00.000Z",
        "contents": {"summary": True},
    })

    if not results:
        return f"No global news found between {start_date} and {curr_date}"

    return f"## Global Market News, from {start_date} to {curr_date}:\n\n{_format_results(results[:limit])}"
