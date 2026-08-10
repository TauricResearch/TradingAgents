"""Firecrawl news vendor.

Ticker and macro news pulled from the open web via Firecrawl's search API
(https://docs.firecrawl.dev/api-reference/endpoint/search), as a complement to
the single-feed vendors: Yahoo and Alpha Vantage return whatever their own wire
carries, so a ticker they cover thinly — non-US listings, small caps, anything
whose coverage lives in trade press or a company newsroom — reads as "no news"
rather than "nothing happened". A web search reaches those sources.

Look-ahead safety is enforced *server-side*: every query pins the search engine's
custom date range (``tbs=cdr:1,cd_min:...,cd_max:...``) to the requested window,
so the API cannot return an article published after ``end_date``. Per-article
dates are deliberately not rendered into the report: recent results carry a
relative age ("1 day ago") measured from now rather than from the analysis date,
which misdates every article in a historical run, and older results carry an
absolute date ("Apr 9, 2024") — mixing the two would read as inconsistent. The
window in the report header is the authoritative date range.

Called over plain REST with ``requests``, like the other vendors here, rather
than through the ``firecrawl-py`` SDK: one endpoint is used, and the SDK would
add aiohttp/websockets/nest-asyncio to the core install for it.

A key (https://www.firecrawl.dev) is read from ``FIRECRAWL_API_KEY``; if it is
unset the vendor raises ``FirecrawlNotConfiguredError`` so the routing layer
treats it as "unavailable" rather than a hard crash.
"""
import logging
import os
import re
import time
from datetime import datetime, timedelta
from urllib.parse import urlparse

import requests

from .config import get_config
from .errors import (
    NoNewsError,
    VendorError,
    VendorNotConfiguredError,
    VendorRateLimitError,
)

logger = logging.getLogger(__name__)

FIRECRAWL_API_BASE = "https://api.firecrawl.dev/v2"

# Network timeout (seconds). Higher than the other vendors' 30: a search is a
# live web query plus aggregation, and an empty result set alone takes ~6s.
REQUEST_TIMEOUT = 60

# Statuses Firecrawl documents as transient
# (https://docs.firecrawl.dev/api-reference/errors).
RETRYABLE_STATUSES = frozenset({408, 429, 500, 502, 503, 504})

# Bounded backoff: two retries, doubling from 2s. Deliberately tighter than
# ``yf_retry``'s budget — each attempt can already take REQUEST_TIMEOUT, and news
# sits on the interactive path, so the worst case is two waits rather than a
# multi-minute stall.
MAX_RETRIES = 2
BASE_RETRY_DELAY = 2.0

# Ceiling on a server-supplied ``Retry-After``, matching the Reddit vendor: an
# outsized or malformed header must not stall an analysis run.
MAX_RETRY_DELAY = 30.0

# Snippets are page extracts and can run to several paragraphs of markdown.
# Cap them so a news report stays within a sensible share of the agent prompt.
MAX_SNIPPET_CHARS = 500

# Markdown images in a snippet are decoration (often inline base64 blobs) and
# carry no signal for an analyst — drop them before truncating.
_MARKDOWN_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")


class FirecrawlNotConfiguredError(VendorNotConfiguredError):
    """Raised when Firecrawl is selected but no API key is configured.

    A VendorNotConfiguredError (and thus still a ValueError), so the routing
    layer's "vendor unavailable" handling and existing ValueError callers both
    keep working.
    """


class FirecrawlRateLimitError(VendorRateLimitError):
    """Raised when the Firecrawl API rate limit is exceeded, retries included."""


class FirecrawlResponseError(VendorError):
    """Raised when Firecrawl returns a body this client cannot interpret.

    Intentionally not one of the router's typed reactions: an uninterpretable
    response is a real fault, so the generic handler logs it, tries the next
    vendor, and surfaces it if none can serve the call. Kept distinct from
    ``NoNewsError`` because a ``success: false`` body or a shape change is not a
    quiet news window — reporting it as "no news" would tell the analyst the
    market was silent when the client merely failed to read the answer.
    """


def get_api_key() -> str:
    """Retrieve the Firecrawl API key from the environment."""
    api_key = os.getenv("FIRECRAWL_API_KEY")
    if not api_key:
        raise FirecrawlNotConfiguredError(
            "FIRECRAWL_API_KEY environment variable is not set. Get a key at "
            "https://www.firecrawl.dev."
        )
    return api_key


def _date_range_tbs(start_date: str, end_date: str) -> str:
    """Build the custom-date-range time filter for a ``yyyy-mm-dd`` window.

    The search engine expects US-style ``M/D/YYYY`` bounds. Built by hand rather
    than with ``strftime`` because the no-zero-pad directive differs across
    platforms (``%-m`` on Linux, ``%#m`` on Windows).
    """
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    return (
        f"cdr:1,cd_min:{start.month}/{start.day}/{start.year},"
        f"cd_max:{end.month}/{end.day}/{end.year}"
    )


def _retry_delay(response, attempt: int) -> float:
    """Seconds to wait before retrying ``response``.

    Firecrawl sends ``Retry-After`` (in seconds) on a 429; honour it when
    present, otherwise back off exponentially. The header's HTTP-date form is
    not parsed — it falls back to the curve rather than guessing at a date.
    """
    header = (response.headers or {}).get("Retry-After")
    if header:
        try:
            return min(float(header), MAX_RETRY_DELAY)
        except (TypeError, ValueError):
            pass
    return min(BASE_RETRY_DELAY * (2**attempt), MAX_RETRY_DELAY)


def _news_results(response) -> list[dict]:
    """Extract ``data.news`` from a 2xx body, rejecting anything else.

    Strict on purpose. The callers turn an empty list into ``NoNewsError``, so
    treating an unreadable body as "no results" would report a client-side
    failure to the analyst as a genuinely quiet news window — and, with Firecrawl
    last in a chain, silently cost the run its news coverage.
    """
    try:
        payload = response.json()
    except ValueError as e:
        raise FirecrawlResponseError(
            f"Firecrawl returned a non-JSON body: {response.text[:200]}"
        ) from e

    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise FirecrawlResponseError(
            f"Firecrawl search did not succeed: {str(payload)[:200]}"
        )

    data = payload.get("data")
    news = data.get("news") if isinstance(data, dict) else None
    if not isinstance(news, list):
        raise FirecrawlResponseError(
            f"Firecrawl response has no 'data.news' list: {str(payload)[:200]}"
        )
    return news


def _search_news(query: str, start_date: str, end_date: str, limit: int) -> list[dict]:
    """POST /search restricted to news results inside the date window.

    Transient statuses are retried with bounded backoff before the error is
    raised. Firecrawl is typically the *last* vendor in a chain, so there is
    nothing left to fall through to: a throttling burst that isn't ridden out
    costs the run its news coverage outright.
    """
    payload = {
        "query": query,
        "sources": [{"type": "news"}],
        "limit": limit,
        "tbs": _date_range_tbs(start_date, end_date),
    }
    headers = {"Authorization": f"Bearer {get_api_key()}"}

    for attempt in range(MAX_RETRIES + 1):
        response = requests.post(
            f"{FIRECRAWL_API_BASE}/search",
            json=payload,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
        if response.status_code not in RETRYABLE_STATUSES or attempt == MAX_RETRIES:
            break
        delay = _retry_delay(response, attempt)
        logger.warning(
            "Firecrawl returned %s for %r; retrying in %.1fs (attempt %d/%d).",
            response.status_code, query, delay, attempt + 1, MAX_RETRIES,
        )
        time.sleep(delay)

    if response.status_code == 429:
        raise FirecrawlRateLimitError(f"Firecrawl rate limit exceeded: {response.text}")
    if response.status_code in (401, 403):
        # Distinguish a bad/expired key from a real outage: the router can skip
        # to the next vendor for "not configured" but must not hide a 5xx. Not
        # retried — a rejected key will be rejected again.
        raise FirecrawlNotConfiguredError(
            f"Firecrawl API key rejected ({response.status_code}): {response.text}"
        )
    response.raise_for_status()
    return _news_results(response)


def _clean_snippet(snippet: str) -> str:
    """Strip markdown images, collapse whitespace, and cap the length."""
    text = " ".join(_MARKDOWN_IMAGE.sub("", snippet or "").split())
    if len(text) > MAX_SNIPPET_CHARS:
        text = text[:MAX_SNIPPET_CHARS].rstrip() + "..."
    return text


def _format_articles(header: str, articles: list[dict]) -> str:
    """Render search results in the same shape as the other news vendors.

    The publishing outlet is taken from the URL host — Firecrawl's news results
    carry no separate publisher field.
    """
    news_str = ""
    for article in articles:
        url = article.get("url", "")
        publisher = urlparse(url).netloc.removeprefix("www.") or "Unknown"
        news_str += f"### {article.get('title', 'No title')} (source: {publisher})\n"
        snippet = _clean_snippet(article.get("snippet", ""))
        if snippet:
            news_str += f"{snippet}\n"
        if url:
            news_str += f"Link: {url}\n"
        news_str += "\n"
    return f"## {header}\n\n{news_str}"


def get_news_firecrawl(ticker: str, start_date: str, end_date: str) -> str:
    """Retrieve news for a specific ticker via Firecrawl web search.

    Args:
        ticker: Ticker symbol (e.g., "AAPL"). Used verbatim in the query — the
            symbol a human would search is a better search term than the
            Yahoo-canonical form other vendors need (``XAUUSD`` beats ``GC=F``).
        start_date: Start date in yyyy-mm-dd format
        end_date: End date in yyyy-mm-dd format

    Returns:
        Formatted string containing news articles

    Raises:
        NoNewsError: The search returned nothing in the window, so the router
            can try the next vendor in the chain.
    """
    limit = get_config()["news_article_limit"]
    articles = _search_news(f"{ticker} stock news", start_date, end_date, limit)

    if not articles:
        raise NoNewsError(f"No news found for {ticker} between {start_date} and {end_date}")

    return _format_articles(f"{ticker} News, from {start_date} to {end_date}", articles)


def get_global_news_firecrawl(
    curr_date: str,
    look_back_days: int | None = None,
    limit: int | None = None,
) -> str:
    """Retrieve global/macro news via Firecrawl web search.

    Args:
        curr_date: Current date in yyyy-mm-dd format
        look_back_days: Number of days to look back. ``None`` falls back to
            ``global_news_lookback_days`` from the active config.
        limit: Maximum number of articles to return. ``None`` falls back to
            ``global_news_article_limit`` from the active config.

    Returns:
        Formatted string containing global news articles

    Raises:
        NoNewsError: The search returned nothing in the window, so the router
            can try the next vendor in the chain.
    """
    config = get_config()
    if look_back_days is None:
        look_back_days = config["global_news_lookback_days"]
    if limit is None:
        limit = config["global_news_article_limit"]

    start_date = (
        datetime.strptime(curr_date, "%Y-%m-%d") - timedelta(days=look_back_days)
    ).strftime("%Y-%m-%d")

    all_news = []
    seen_urls = set()
    for query in config["global_news_queries"]:
        for article in _search_news(query, start_date, curr_date, limit):
            url = article.get("url")
            # Deduplicate by URL: the macro queries overlap, and the same wire
            # story is syndicated under slightly different titles.
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_news.append(article)

        if len(all_news) >= limit:
            break

    if not all_news:
        raise NoNewsError(f"No global news found between {start_date} and {curr_date}")

    return _format_articles(
        f"Global Market News, from {start_date} to {curr_date}", all_news[:limit]
    )
