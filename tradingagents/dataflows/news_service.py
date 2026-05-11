"""News service client for fetching A-share / HK stock news from the news server API."""

import os
import re
import requests
from typing import Optional
from datetime import datetime, timedelta, timezone

from .config import get_config

# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------

DEFAULT_NEWS_SERVER_BASE_URL = "https://news.zehb.cn:228"
REQUEST_TIMEOUT = 5  # seconds

# Beijing time zone (UTC+8)
_BEIJING_TZ = timezone(timedelta(hours=8))


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _get_config() -> dict:
    """Return news service connection configuration from environment variables."""
    return {
        "base_url": os.getenv("NEWS_SERVER_BASE_URL", DEFAULT_NEWS_SERVER_BASE_URL),
        "api_key": os.getenv("NEWS_SERVER_API_KEY", ""),
        "proxy": os.getenv("NEWS_SERVER_PROXY", ""),
    }


def _make_request(endpoint: str, params: dict = None) -> dict:
    """
    Send a GET request to the news service API.

    Args:
        endpoint: API endpoint path (e.g. "/api/v1/news/by-stock/600519")
        params: Optional query parameters

    Returns:
        Parsed JSON response as dict

    Raises:
        RuntimeError: On authentication failure, timeout, or connection error
    """
    cfg = _get_config()
    base_url = cfg["base_url"].rstrip("/")
    api_key = cfg["api_key"]
    proxy = cfg["proxy"]

    url = f"{base_url}{endpoint}"
    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json",
    }
    proxies = None
    if proxy:
        proxies = {"http": proxy, "https": proxy}

    try:
        resp = requests.get(
            url,
            headers=headers,
            params=params,
            proxies=proxies,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.exceptions.Timeout:
        raise RuntimeError(f"Request timed out: {url}")
    except requests.exceptions.ConnectionError as e:
        raise RuntimeError(f"Connection error: {e}")
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Request failed: {e}")

    if resp.status_code == 401 or resp.status_code == 403:
        raise RuntimeError("Authentication failed: invalid or missing API key")
    if resp.status_code != 200:
        raise RuntimeError(
            f"API returned status {resp.status_code}: {resp.text[:200]}"
        )

    return resp.json()


def _format_news_item(item: dict) -> str:
    """
    Format a single news item dict into Markdown.

    Expected item keys: title, source_name, summary/content, url.
    """
    title = item.get("title", "No title")
    source_name = item.get("source_name", "Unknown")
    summary = item.get("summary") or (item.get("content", "") or "")[:200]
    url = item.get("url", "")

    text = f"### {title} (source: {source_name})\n"
    if summary:
        text += f"{summary}\n"
    if url:
        text += f"Link: {url}\n"
    text += "\n"
    return text


def _extract_stock_code(ticker: str) -> str:
    """
    Extract pure numeric stock code from various ticker formats.

    Examples:
        "600519.SH" -> "600519"
        "SH600519"  -> "600519"
        "600519"    -> "600519"
        "000001.SZ" -> "000001"
    """
    # Remove known exchange suffixes like .SH, .SZ, .HK, etc.
    if "." in ticker:
        code = ticker.split(".")[0]
        # If the part before dot is numeric, use it directly
        if code.isdigit():
            return code

    # Handle prefix formats: SH600519, SZ000001
    match = re.match(r"^[A-Za-z]{2}(\d+)$", ticker)
    if match:
        return match.group(1)

    # If it's already pure digits
    if ticker.isdigit():
        return ticker

    # Fallback: extract all digits
    digits = re.findall(r"\d+", ticker)
    return digits[0] if digits else ticker


def _date_to_iso(date_str: str) -> str:
    """
    Convert a yyyy-mm-dd date string to ISO 8601 with Beijing timezone.

    Example: "2024-01-15" -> "2024-01-15T00:00:00+08:00"
    """
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    dt_bj = dt.replace(tzinfo=_BEIJING_TZ)
    return dt_bj.isoformat()


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def get_news_service_news(ticker: str, start_date: str, end_date: str) -> str:
    """
    Fetch news for a specific stock from the news service API.

    Args:
        ticker: Stock ticker (e.g. "600519.SH", "SH600519", "600519")
        start_date: Start date in yyyy-mm-dd format
        end_date: End date in yyyy-mm-dd format

    Returns:
        Formatted Markdown string with news articles, or an error/empty message.
    """
    # Check API key first
    cfg = _get_config()
    if not cfg["api_key"]:
        return f"No news found for {ticker}: NEWS_SERVER_API_KEY not configured"

    # Determine article limit from project config (fallback to 20)
    try:
        project_cfg = get_config()
        article_limit = project_cfg.get("news_article_limit", 20)
    except Exception:
        article_limit = 20

    code = _extract_stock_code(ticker)
    iso_start = _date_to_iso(start_date)
    iso_end = _date_to_iso(end_date)

    seen_titles: set = set()
    all_items: list = []

    try:
        # 1) Fetch by stock endpoint
        try:
            data = _make_request(
                f"/api/v1/news/by-stock/{code}",
                params={"limit": article_limit, "sort_by": "published_at"},
            )
            items = data if isinstance(data, list) else data.get("data", data.get("items", []))
            for item in items:
                title = item.get("title", "")
                if title and title not in seen_titles:
                    seen_titles.add(title)
                    all_items.append(item)
        except RuntimeError:
            pass  # Continue to try the date-filtered endpoint

        # 2) Fetch with date range filter
        try:
            data = _make_request(
                "/api/v1/news",
                params={
                    "stock_code": code,
                    "start_date": iso_start,
                    "end_date": iso_end,
                    "limit": article_limit,
                    "sort_by": "importance",
                },
            )
            items = data if isinstance(data, list) else data.get("data", data.get("items", []))
            for item in items:
                title = item.get("title", "")
                if title and title not in seen_titles:
                    seen_titles.add(title)
                    all_items.append(item)
        except RuntimeError:
            pass

        if not all_items:
            return f"No news found for {ticker} between {start_date} and {end_date}"

        # Format output
        news_str = ""
        for item in all_items[:article_limit]:
            news_str += _format_news_item(item)

        return f"## {ticker} News, from {start_date} to {end_date}:\n\n{news_str}"

    except Exception as e:
        return f"Error fetching news for {ticker}: {str(e)}"


def get_news_service_global_news(
    curr_date: str,
    look_back_days: Optional[int] = None,
    limit: Optional[int] = None,
) -> str:
    """
    Fetch global/macro market news from the news service API.

    Args:
        curr_date: Current date in yyyy-mm-dd format
        look_back_days: Number of days to look back (default from config or 7)
        limit: Maximum number of articles (default from config or 10)

    Returns:
        Formatted Markdown string with global news articles, or an error/empty message.
    """
    # Check API key first
    cfg = _get_config()
    if not cfg["api_key"]:
        return f"No news found for global market: NEWS_SERVER_API_KEY not configured"

    # Resolve defaults from project config
    try:
        project_cfg = get_config()
        if look_back_days is None:
            look_back_days = project_cfg.get("global_news_lookback_days", 7)
        if limit is None:
            limit = project_cfg.get("global_news_article_limit", 10)
    except Exception:
        if look_back_days is None:
            look_back_days = 7
        if limit is None:
            limit = 10

    # Calculate date range
    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_dt = curr_dt - timedelta(days=look_back_days)
    start_date = start_dt.strftime("%Y-%m-%d")

    iso_start = _date_to_iso(start_date)
    iso_end = _date_to_iso(curr_date)

    seen_titles: set = set()
    all_items: list = []

    try:
        # 1) Fetch macro/宏观 category news
        try:
            data = _make_request(
                "/api/v1/news",
                params={
                    "category": "宏观",
                    "start_date": iso_start,
                    "end_date": iso_end,
                    "limit": limit,
                    "sort_by": "importance",
                },
            )
            items = data if isinstance(data, list) else data.get("data", data.get("items", []))
            for item in items:
                title = item.get("title", "")
                if title and title not in seen_titles:
                    seen_titles.add(title)
                    all_items.append(item)
        except RuntimeError:
            pass

        # 2) If not enough results, fetch from summary endpoint
        if len(all_items) < limit:
            try:
                data = _make_request(
                    "/api/v1/news/summary",
                    params={
                        "start_date": iso_start,
                        "end_date": iso_end,
                        "sort_by": "importance",
                    },
                )
                summary_items = data if isinstance(data, list) else data.get("data", data.get("items", []))

                # For summary items, fetch detail if they have news_id
                detail_fetched = 0
                for summary_item in summary_items:
                    if len(all_items) >= limit:
                        break

                    title = summary_item.get("title", "")
                    if title and title in seen_titles:
                        continue

                    news_id = summary_item.get("id") or summary_item.get("news_id")
                    if news_id and detail_fetched < 5:
                        # Fetch full detail
                        try:
                            detail = _make_request(f"/api/v1/news/{news_id}")
                            detail_item = detail if isinstance(detail, dict) and "title" in detail else detail.get("data", detail)
                            if isinstance(detail_item, dict):
                                detail_title = detail_item.get("title", "")
                                if detail_title and detail_title not in seen_titles:
                                    seen_titles.add(detail_title)
                                    all_items.append(detail_item)
                                    detail_fetched += 1
                        except RuntimeError:
                            # Fall back to summary item itself
                            if title:
                                seen_titles.add(title)
                                all_items.append(summary_item)
                    elif title:
                        seen_titles.add(title)
                        all_items.append(summary_item)
            except RuntimeError:
                pass

        if not all_items:
            return f"No global news found for {curr_date}"

        # Format output
        news_str = ""
        for item in all_items[:limit]:
            news_str += _format_news_item(item)

        return f"## Global Market News, from {start_date} to {curr_date}:\n\n{news_str}"

    except Exception as e:
        return f"Error fetching global news: {str(e)}"
