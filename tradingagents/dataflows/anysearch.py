"""AnySearch global-news vendor (live-only supplement).

AnySearch (https://api.anysearch.com) is a real-time web/news search API for
agents. It is offered here as an *opt-in supplement* for ``get_global_news``
only, never for ticker-level news or any price/indicator data.

Critical look-ahead guardrail
------------------------------
AnySearch results carry ``title / url / snippet / content`` but **no reliable
structured publish date** (verified against the live ``/v1/search`` response).
There is therefore no way to bound results to a historical window, so using
AnySearch for a backtest date would leak future news into the past. To stay
look-ahead-safe this vendor **only serves a live window** — one whose end date
(``curr_date``) reaches the present. For any historical ``curr_date`` it raises
``NoMarketDataError`` so the router transparently falls back to yfinance, which
*does* date-filter (#992/#1007 semantics).

Auth: optional ``ANYSEARCH_API_KEY`` (Bearer). Anonymous access works with
lower rate limits. Uses ``requests`` (already a core dependency); no new extra.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import requests

from .config import get_config
from .errors import NoMarketDataError, VendorRateLimitError

_ANYSEARCH_SEARCH_URL = "https://api.anysearch.com/v1/search"
_ANYSEARCH_CLIENT_HEADER = "tradingagents/1.0"

# A live run's end date may lag "now" by up to this many days (weekend/holiday,
# or a run kicked off for "today" a little after midnight UTC). Beyond this the
# window is treated as historical and AnySearch is refused (look-ahead safety).
_LIVE_WINDOW_TOLERANCE_DAYS = 2

# Per-request network timeout (connect, read) in seconds.
_ANYSEARCH_TIMEOUT = 30


def _is_live_window(curr_date: str) -> bool:
    """Whether ``curr_date`` is recent enough to be a live (not backtest) run.

    AnySearch cannot date-filter, so we only allow it when the requested end
    date is at/after (today - tolerance). A clearly historical date returns
    False and the caller raises NoMarketDataError to fall back to yfinance.
    """
    curr = datetime.strptime(curr_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    today = datetime.now(timezone.utc)
    return curr.date() >= (today - timedelta(days=_LIVE_WINDOW_TOLERANCE_DAYS)).date()


def get_anysearch_global_news(
    curr_date: str,
    look_back_days: int | None = None,
    limit: int | None = None,
) -> str:
    """Fetch global/macro news from AnySearch — LIVE runs only.

    Signature mirrors ``get_global_news_yfinance`` so it drops into the
    ``get_global_news`` vendor slot. For a historical ``curr_date`` this raises
    ``NoMarketDataError`` (no reliable date on results -> would leak future news
    into a backtest), letting the router fall back to a date-filtering vendor.
    """
    config = get_config()
    if look_back_days is None:
        look_back_days = config["global_news_lookback_days"]
    if limit is None:
        limit = config["global_news_article_limit"]

    if not _is_live_window(curr_date):
        # Look-ahead guard: AnySearch results are undated, so they cannot be
        # constrained to a past window. Refuse historical dates so the router
        # falls back to yfinance (which filters by publish date).
        raise NoMarketDataError(
            "GLOBAL_NEWS",
            "GLOBAL_NEWS",
            f"AnySearch is live-only (results carry no publish date); "
            f"{curr_date} is a historical date, so it cannot be date-bounded "
            f"without leaking future news — falling back to a dated vendor.",
        )

    search_queries = config["global_news_queries"]
    headers = {
        "Content-Type": "application/json",
        "X-Anysearch-Client": _ANYSEARCH_CLIENT_HEADER,
    }
    api_key = os.environ.get("ANYSEARCH_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    # Cap per-query results at the API's max (10) and the configured limit.
    per_query = max(1, min(int(limit), 10))

    all_items: list[dict] = []
    seen_urls: set[str] = set()
    for query in search_queries:
        try:
            resp = requests.post(
                _ANYSEARCH_SEARCH_URL,
                json={
                    "query": query,
                    "max_results": per_query,
                    "content_types": ["news"],
                },
                headers=headers,
                timeout=_ANYSEARCH_TIMEOUT,
            )
        except requests.RequestException as exc:
            # A transient network error should let another vendor try, not crash.
            raise NoMarketDataError(
                "GLOBAL_NEWS", "GLOBAL_NEWS", f"AnySearch request failed: {exc}"
            ) from exc

        if resp.status_code == 429:
            raise VendorRateLimitError(
                f"AnySearch rate limit hit (HTTP 429) for query {query!r}."
            )
        if resp.status_code != 200:
            raise NoMarketDataError(
                "GLOBAL_NEWS",
                "GLOBAL_NEWS",
                f"AnySearch returned HTTP {resp.status_code}.",
            )

        payload = resp.json()
        # API envelope: {"code": 0, "data": {"results": [...]}}; code != 0 = error.
        if payload.get("code") != 0:
            raise NoMarketDataError(
                "GLOBAL_NEWS",
                "GLOBAL_NEWS",
                f"AnySearch error: {payload.get('message', 'unknown')}.",
            )
        for item in (payload.get("data") or {}).get("results") or []:
            url = item.get("url", "")
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)
            all_items.append(item)
        if len(all_items) >= limit:
            break

    if not all_items:
        raise NoMarketDataError(
            "GLOBAL_NEWS", "GLOBAL_NEWS", "AnySearch returned no news results."
        )

    start_dt = datetime.strptime(curr_date, "%Y-%m-%d") - timedelta(days=look_back_days)
    start_date = start_dt.strftime("%Y-%m-%d")

    lines = [
        f"## Global Market News (AnySearch, live), around {start_date} to {curr_date}:",
        "",
        "_Source: AnySearch real-time web search. Items are undated; this is a "
        "live snapshot, not a date-bounded historical window._",
        "",
    ]
    for item in all_items[:limit]:
        title = item.get("title", "Untitled")
        snippet = item.get("snippet", "") or ""
        url = item.get("url", "")
        lines.append(f"### {title}")
        if snippet:
            lines.append(snippet)
        if url:
            lines.append(f"Link: {url}")
        lines.append("")

    return "\n".join(lines)
