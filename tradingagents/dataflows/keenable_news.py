"""Keenable web-search news vendor.

Searches the open web for ticker news (``get_news``) and macro headlines
(``get_global_news``) inside the analysis window and returns them in the same
report shape as the yfinance news vendor, so the news and sentiment analysts
read them unchanged.

Uses Keenable's search API (https://api.keenable.ai). No account is needed: the
default path is the keyless ``/v1/search/public`` endpoint, which only asks for
an ``X-Keenable-Title`` header naming the calling application. Setting
``KEENABLE_API_KEY`` switches to the keyed ``/v1/search`` endpoint; the key only
lifts the per-IP rate limits, it is not a prerequisite.

Look-ahead safety: the request itself is bounded with ``published_after`` /
``published_before`` so the service never returns an article dated after the
window, and every result is then re-checked client-side with the shared
``date_window.in_window`` rule (UTC, half-open at midnight after ``end_date``)
before it reaches the agent, like every other dated source.
"""

from __future__ import annotations

import contextlib
import logging
import os
import re
from datetime import datetime, timedelta
from urllib.parse import urlparse

import requests

from .config import get_config
from .date_window import in_window
from .errors import VendorRateLimitError
from .symbol_utils import crypto_base

logger = logging.getLogger(__name__)

KEENABLE_API_BASE = "https://api.keenable.ai/v1"
PUBLIC_SEARCH_URL = f"{KEENABLE_API_BASE}/search/public"
KEYED_SEARCH_URL = f"{KEENABLE_API_BASE}/search"

# Names the calling application on every request. Mandatory on the keyless
# endpoint (the service rejects a request without it).
APP_TITLE = "tradingagents"

# Network timeout (seconds), consistent with the other vendors.
REQUEST_TIMEOUT = 30

# Snippet budget per article, in characters. The service treats
# ``snippet_max_length`` as a hint (it rounds up to a word boundary), so the
# text is also sliced here to keep the agent prompt bounded.
SNIPPET_MAX_LENGTH = 600

# Hard cap the service accepts for ``max_results``.
MAX_RESULTS = 50

_WHITESPACE = re.compile(r"\s+")


class KeenableRateLimitError(VendorRateLimitError):
    """Raised when Keenable throttles the request (HTTP 429).

    A ``VendorRateLimitError``, so the routing layer skips to the next vendor in
    the configured chain instead of treating an empty body as a clean result.
    """


def _api_key() -> str | None:
    """Optional API key; ``None`` (the default) selects the keyless endpoint."""
    return os.getenv("KEENABLE_API_KEY") or None


def _request(payload: dict) -> dict:
    """POST a search to Keenable, keyed when a key is configured, keyless otherwise.

    Raises:
        KeenableRateLimitError: on HTTP 429, carrying the service's retry hint.
        requests.HTTPError: on any other non-2xx status, with the service's
            error message attached so a malformed request is diagnosable.
    """
    headers = {"Content-Type": "application/json", "X-Keenable-Title": APP_TITLE}
    api_key = _api_key()
    if api_key:
        headers["X-API-Key"] = api_key
        url = KEYED_SEARCH_URL
    else:
        url = PUBLIC_SEARCH_URL

    response = requests.post(url, json=payload, headers=headers, timeout=REQUEST_TIMEOUT)

    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After")
        hint = f"; retry after {retry_after}s" if retry_after else ""
        raise KeenableRateLimitError(f"Keenable rate limit exceeded{hint}")

    if not response.ok:
        # Error bodies are JSON {"error": ..., "message": ...}; surface the
        # message rather than a bare status code.
        try:
            message = response.json().get("message") or response.text
        except ValueError:
            message = response.text
        raise requests.HTTPError(
            f"Keenable request failed ({response.status_code}): {message}",
            response=response,
        )

    return response.json()


def _search(query: str, start_dt: datetime, end_dt: datetime, limit: int) -> list[dict]:
    """Run one windowed search and return its raw result dicts."""
    payload = {
        "query": query,
        "max_results": max(1, min(int(limit), MAX_RESULTS)),
        "snippet_max_length": SNIPPET_MAX_LENGTH,
        # Half-open window [start, end + 1 day), matching date_window.in_window.
        "published_after": start_dt.strftime("%Y-%m-%d"),
        "published_before": (end_dt + timedelta(days=1)).strftime("%Y-%m-%d"),
    }
    data = _request(payload)
    results = data.get("results") if isinstance(data, dict) else None
    return results if isinstance(results, list) else []


def _parse_timestamp(raw) -> datetime | None:
    """Parse an ISO 8601 timestamp (``Z`` suffix allowed); ``None`` when absent or malformed."""
    if not raw:
        return None
    with contextlib.suppress(ValueError, TypeError, AttributeError):
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    return None


def _source(url: str) -> str:
    """Publisher label for the report header: the URL's host without ``www.``."""
    host = urlparse(url).netloc if url else ""
    return host[4:] if host.startswith("www.") else host or "unknown"


def _clean_snippet(result: dict) -> str:
    """Article text for the agent: ``snippet`` (page text) first, ``description`` as fallback.

    Whitespace is collapsed and the text is sliced to ``SNIPPET_MAX_LENGTH`` so
    one long page can't flood the prompt.
    """
    text = result.get("snippet") or result.get("description") or ""
    text = _WHITESPACE.sub(" ", str(text)).strip()
    if len(text) > SNIPPET_MAX_LENGTH:
        text = text[:SNIPPET_MAX_LENGTH].rstrip() + "…"
    return text


def _build_query(ticker: str) -> str:
    """Search query for a ticker; crypto pairs search by their base asset."""
    base = crypto_base(ticker)
    if base:
        return f"{base} crypto news"
    return f"{ticker.strip().upper()} stock news"


def _format_articles(
    results: list[dict], start_dt: datetime, end_dt: datetime, limit: int
) -> tuple[str, int]:
    """Render in-window, deduplicated results as report sections.

    Returns the rendered body and the number of articles kept.
    """
    news_str = ""
    kept = 0
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    for result in results:
        if kept >= limit:
            break
        title = (result.get("title") or "").strip() or "No title"
        url = (result.get("url") or "").strip()

        # The same story is often syndicated under several URLs; keep one copy.
        title_key = title.lower()
        if url in seen_urls or title_key in seen_titles:
            continue

        # Publication time when the service has it, else the time the page was
        # first seen (an upper bound on publication, so still look-ahead safe).
        pub_dt = _parse_timestamp(result.get("published_at")) or _parse_timestamp(
            result.get("acquired_at")
        )
        if not in_window(pub_dt, start_dt, end_dt):
            continue

        seen_urls.add(url)
        seen_titles.add(title_key)

        news_str += f"### {title} (source: {_source(url)})\n"
        if pub_dt is not None:
            news_str += f"Published: {pub_dt.strftime('%Y-%m-%d')}\n"
        snippet = _clean_snippet(result)
        if snippet:
            news_str += f"{snippet}\n"
        if url:
            news_str += f"Link: {url}\n"
        news_str += "\n"
        kept += 1
    return news_str, kept


def get_news_keenable(
    ticker: str,
    start_date: str,
    end_date: str,
) -> str:
    """Retrieve news for a stock ticker from a Keenable web search.

    Args:
        ticker: Stock ticker symbol (e.g., "AAPL")
        start_date: Start date in yyyy-mm-dd format
        end_date: End date in yyyy-mm-dd format

    Returns:
        Formatted string containing news articles, in the same shape as the
        yfinance news vendor (title, source, published date, snippet, link).
    """
    article_limit = get_config()["news_article_limit"]
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    try:
        results = _search(_build_query(ticker), start_dt, end_dt, article_limit)
    except KeenableRateLimitError:
        raise  # the router skips to the next configured vendor
    except (requests.RequestException, ValueError) as e:
        logger.warning("Keenable news fetch failed for %s: %s", ticker, e)
        return f"Error fetching news for {ticker} from Keenable: {e}"

    news_str, kept = _format_articles(results, start_dt, end_dt, article_limit)
    if kept == 0:
        return f"No news found for {ticker} between {start_date} and {end_date}"

    return f"## {ticker} News, from {start_date} to {end_date}:\n\n{news_str}"


def get_global_news_keenable(
    curr_date: str,
    look_back_days: int | None = None,
    limit: int | None = None,
) -> str:
    """Retrieve global/macro news from Keenable web searches.

    Runs the configured ``global_news_queries`` in order, each bounded to the
    window, and stops once ``limit`` distinct articles are collected.

    Args:
        curr_date: Current date in yyyy-mm-dd format
        look_back_days: Number of days to look back. ``None`` falls back to
            ``global_news_lookback_days`` from the active config.
        limit: Maximum number of articles to return. ``None`` falls back to
            ``global_news_article_limit`` from the active config.

    Returns:
        Formatted string containing global news articles
    """
    config = get_config()
    if look_back_days is None:
        look_back_days = config["global_news_lookback_days"]
    if limit is None:
        limit = config["global_news_article_limit"]
    search_queries = config["global_news_queries"]

    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_dt = curr_dt - timedelta(days=look_back_days)
    start_date = start_dt.strftime("%Y-%m-%d")

    all_results: list[dict] = []
    try:
        for query in search_queries:
            all_results.extend(_search(query, start_dt, curr_dt, limit))
            # Rough early exit; the final dedup/window pass enforces the cap.
            if len(all_results) >= limit:
                break
    except KeenableRateLimitError:
        raise
    except (requests.RequestException, ValueError) as e:
        logger.warning("Keenable global news fetch failed: %s", e)
        return f"Error fetching global news from Keenable: {e}"

    news_str, kept = _format_articles(all_results, start_dt, curr_dt, limit)
    if kept == 0:
        return f"No global news found between {start_date} and {curr_date}"

    return f"## Global Market News, from {start_date} to {curr_date}:\n\n{news_str}"
