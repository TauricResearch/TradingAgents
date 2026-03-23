"""Bright Data integration for TradingAgents.

Uses SERP API for search results and Web Unlocker for full article content
in clean markdown format. No HTML parsing needed.

- SERP API docs: https://docs.brightdata.com/scraping-automation/serp-api/introduction
- Web Unlocker docs: https://docs.brightdata.com/scraping-automation/web-unlocker/introduction
"""

import os
import requests
from datetime import datetime, timedelta


class BrightDataError(Exception):
    """Base exception for Bright Data API errors."""

    pass


class BrightDataRateLimitError(BrightDataError):
    """Raised when rate limited by Bright Data API."""

    pass


def _get_api_key() -> str:
    key = os.environ.get("BRIGHT_DATA_API_KEY", "")
    if not key:
        raise BrightDataError(
            "BRIGHT_DATA_API_KEY not set. Get one at https://brightdata.com"
        )
    return key


def _get_zone(zone_type: str) -> str:
    """Get zone name from env or use defaults."""
    if zone_type == "serp":
        return os.environ.get("BRIGHT_DATA_SERP_ZONE", "serp_api1")
    return os.environ.get("BRIGHT_DATA_UNLOCKER_ZONE", "web_unlocker1")


# ── SERP API ─────────────────────────────────────────────────────────


def _serp_search(query: str, num_results: int = 10) -> list[dict]:
    """Search Google via Bright Data SERP API. Returns parsed organic results.

    Args:
        query: Google search query.
        num_results: Number of results to request.

    Returns:
        List of dicts with keys: title, link, description.
    """
    api_key = _get_api_key()
    search_url = f"https://www.google.com/search?q={requests.utils.quote(query)}&num={num_results}&brd_json=1"

    resp = requests.post(
        "https://api.brightdata.com/request",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        json={
            "zone": _get_zone("serp"),
            "url": search_url,
            "format": "json",
        },
        timeout=60,
    )

    if resp.status_code == 429:
        raise BrightDataRateLimitError("SERP API rate limit exceeded")
    resp.raise_for_status()

    data = resp.json()

    # Parse organic results from SERP response
    # The SERP API wraps results in a "body" key as a JSON string
    body = data.get("body", data)
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except json.JSONDecodeError:
            body = data
    organic = body.get("organic", []) if isinstance(body, dict) else []

    results = []
    for item in organic[:num_results]:
        results.append(
            {
                "title": item.get("title", ""),
                "link": item.get("link", ""),
                "description": item.get("description", item.get("snippet", "")),
            }
        )

    return results


# ── Web Unlocker ─────────────────────────────────────────────────────


def _fetch_markdown(url: str) -> str:
    """Fetch a URL via Web Unlocker and return content as clean markdown.

    Args:
        url: Target URL to fetch.

    Returns:
        Page content as markdown string.
    """
    api_key = _get_api_key()

    resp = requests.post(
        "https://api.brightdata.com/request",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        json={
            "zone": _get_zone("unlocker"),
            "url": url,
            "format": "json",
            "data_format": "markdown",
        },
        timeout=60,
    )

    if resp.status_code == 429:
        raise BrightDataRateLimitError("Web Unlocker rate limit exceeded")
    resp.raise_for_status()

    data = resp.json()
    return data.get("body", "")


# ── Combined: Search + Fetch ─────────────────────────────────────────


def _search_and_fetch(
    query: str,
    num_results: int = 5,
    fetch_content: bool = True,
    max_content_length: int = 2000,
) -> list[dict]:
    """Search via SERP API, then fetch top results via Web Unlocker as markdown.

    Args:
        query: Search query.
        num_results: Number of SERP results to fetch.
        fetch_content: If True, fetches full page content for each result.
        max_content_length: Truncate content to this length per result.

    Returns:
        List of dicts with title, link, description, and optionally content.
    """
    results = _serp_search(query, num_results=num_results)

    if fetch_content:
        for r in results:
            link = r.get("link", "")
            if not link:
                continue
            try:
                content = _fetch_markdown(link)
                if len(content) > max_content_length:
                    content = content[:max_content_length] + "\n[... truncated ...]"
                r["content"] = content
            except Exception as e:
                r["content"] = f"[Content fetch failed: {e}]"

    return results


def _format_results(results: list[dict], header: str) -> str:
    """Format search results into a readable string for the LLM agent."""
    if not results:
        return f"No results found for: {header}"

    output = f"## {header}\n\n"
    for r in results:
        title = r.get("title", "Untitled")
        source = r.get("link", "")
        description = r.get("description", "")
        content = r.get("content", "")

        output += f"### {title}\n"
        if description:
            output += f"{description}\n"
        if source:
            output += f"Source: {source}\n"
        if content:
            output += f"\n{content}\n"
        output += "\n"

    return output


# ── Vendor functions (match TradingAgents signatures) ─────────────


def get_news(ticker: str, start_date: str, end_date: str) -> str:
    """Retrieve news for a specific stock ticker using Bright Data SERP API + Web Unlocker.

    Args:
        ticker: Stock ticker symbol (e.g., "AAPL")
        start_date: Start date in yyyy-mm-dd format
        end_date: End date in yyyy-mm-dd format

    Returns:
        Formatted string containing news articles with full markdown content.
    """
    try:
        results = _search_and_fetch(
            query=f"{ticker} stock news {start_date} {end_date}",
            num_results=5,
            fetch_content=True,
        )
        return _format_results(
            results, f"{ticker} News, from {start_date} to {end_date}"
        )
    except BrightDataRateLimitError:
        raise
    except Exception as e:
        return f"Error fetching news for {ticker} via Bright Data: {str(e)}"


def get_global_news(curr_date: str, look_back_days: int = 7, limit: int = 10) -> str:
    """Retrieve global/macro economic news using Bright Data SERP API + Web Unlocker.

    Args:
        curr_date: Current date in yyyy-mm-dd format
        look_back_days: Number of days to look back
        limit: Maximum number of articles to return

    Returns:
        Formatted string containing global news articles with full markdown content.
    """
    try:
        curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
        start_dt = curr_dt - timedelta(days=look_back_days)
        start_date = start_dt.strftime("%Y-%m-%d")

        results = _search_and_fetch(
            query=f"stock market financial news economy {start_date}",
            num_results=min(limit, 5),
            fetch_content=True,
        )
        return _format_results(
            results,
            f"Global Market News, from {start_date} to {curr_date}",
        )
    except BrightDataRateLimitError:
        raise
    except Exception as e:
        return f"Error fetching global news via Bright Data: {str(e)}"


def get_insider_transactions(symbol: str) -> str:
    """Retrieve insider transaction news using Bright Data SERP API + Web Unlocker.

    Args:
        symbol: Ticker symbol (e.g., "IBM")

    Returns:
        Formatted string containing insider transaction reports.
    """
    try:
        results = _search_and_fetch(
            query=f"{symbol} insider trading SEC filing transactions",
            num_results=5,
            fetch_content=True,
        )
        return _format_results(results, f"{symbol} Insider Transactions")
    except BrightDataRateLimitError:
        raise
    except Exception as e:
        return f"Error fetching insider transactions for {symbol} via Bright Data: {str(e)}"


def get_social_sentiment(ticker: str, curr_date: str = "") -> str:
    """Retrieve social media sentiment using Bright Data SERP API + Web Unlocker.

    Searches Reddit, Twitter/X, and financial forums for real retail investor
    discussions. This is a NEW data source not available in yfinance or Alpha Vantage.

    Args:
        ticker: Stock ticker symbol (e.g., "NVDA")
        curr_date: Current date in yyyy-mm-dd format (optional)

    Returns:
        Formatted string containing social media sentiment data.
    """
    try:
        results = _search_and_fetch(
            query=f"{ticker} stock reddit wallstreetbets sentiment discussion",
            num_results=5,
            fetch_content=True,
            max_content_length=3000,
        )
        return _format_results(results, f"{ticker} Social Media Sentiment")
    except BrightDataRateLimitError:
        raise
    except Exception as e:
        return f"Error fetching social sentiment for {ticker} via Bright Data: {str(e)}"
