"""Polygon news + insider-transactions endpoints.

Both endpoints accept date-range filters and date-stamped responses, making
them strict-PIT for backtest replay. ``get_news`` and ``get_global_news``
mirror the yfinance-side signatures so the vendor router can swap providers
without touching agent code.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Any

from .polygon_common import (
    PolygonError,
    PolygonNotFoundError,
    _make_request,
    paginated_results,
)


def _format_news_entries(entries: list[dict[str, Any]], header_label: str) -> str:
    if not entries:
        return f"# {header_label}\n# No news found in the requested window\n"

    lines = [f"# {header_label}", f"# Source: Polygon", f"# Total items: {len(entries)}\n"]
    for item in entries:
        published = item.get("published_utc", "")
        title = item.get("title", "(untitled)")
        publisher_obj = item.get("publisher") or {}
        publisher = publisher_obj.get("name", "Unknown") if isinstance(publisher_obj, dict) else str(publisher_obj)
        url = item.get("article_url") or item.get("url") or ""
        description = item.get("description", "") or ""
        # Trim long descriptions to keep the prompt reasonably sized
        if len(description) > 500:
            description = description[:500].rsplit(" ", 1)[0] + "..."
        keywords = ", ".join(item.get("keywords", []) or [])

        lines.append(f"## {title}")
        lines.append(f"- Published: {published}")
        lines.append(f"- Publisher: {publisher}")
        if keywords:
            lines.append(f"- Keywords: {keywords}")
        if url:
            lines.append(f"- URL: {url}")
        if description:
            lines.append(f"- Summary: {description}")
        lines.append("")

    return "\n".join(lines)


def _date_window(curr_date: str | None, lookback_days: int = 7) -> tuple[str, str]:
    """Default to a 7-day window ending on curr_date (or today)."""
    if curr_date:
        end_dt = datetime.strptime(curr_date[:10], "%Y-%m-%d")
    else:
        end_dt = datetime.utcnow()
    start_dt = end_dt - timedelta(days=lookback_days)
    return start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d")


def get_news(
    ticker: Annotated[str, "ticker symbol"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """Fetch ticker-specific news from Polygon's news endpoint.

    Filters to articles published in ``[start_date, end_date)`` (PIT-safe
    when the caller passes a backtest-aware end_date).
    """
    params: dict[str, Any] = {
        "ticker": ticker.upper(),
        "published_utc.gte": start_date,
        "published_utc.lt": end_date,
        "order": "desc",
        "limit": 50,
    }
    try:
        results = paginated_results("/v2/reference/news", params, max_pages=2)
    except PolygonNotFoundError:
        return f"No news found for {ticker} between {start_date} and {end_date}"
    except PolygonError as exc:
        return f"Error retrieving news for {ticker}: {exc}"

    return _format_news_entries(
        results,
        f"News for {ticker.upper()} from {start_date} to {end_date}",
    )


def get_global_news(
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"],
    look_back_days: Annotated[int, "how many days of news to fetch"] = 7,
    limit: Annotated[int, "max articles to return"] = 10,
) -> str:
    """Fetch broad market news (no ticker filter) from Polygon."""
    start_date, end_date = _date_window(curr_date, look_back_days)

    params: dict[str, Any] = {
        "published_utc.gte": start_date,
        "published_utc.lt": end_date,
        "order": "desc",
        "limit": min(int(limit) * 5, 50),  # over-fetch then trim to limit
    }
    try:
        results = paginated_results("/v2/reference/news", params, max_pages=2)
    except PolygonError as exc:
        return f"Error retrieving global news: {exc}"

    return _format_news_entries(
        results[: int(limit)],
        f"Global market news from {start_date} to {end_date}",
    )


def get_insider_transactions(
    ticker: Annotated[str, "ticker symbol"],
) -> str:
    """Insider Form-4 transactions from Polygon.

    Polygon's Stocks Starter plan does not include the SEC insider
    transactions endpoint; this raises :class:`PolygonError` so the vendor
    router transparently falls through to alpha_vantage / yfinance instead
    of returning an empty payload that downstream agents would have to
    parse around.
    """
    raise PolygonError(
        "Polygon insider transactions endpoint requires Insider Transactions "
        "add-on — falling back to next vendor"
    )
