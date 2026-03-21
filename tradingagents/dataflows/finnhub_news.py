"""Finnhub news and insider transaction functions.

Provides company-specific news, broad market news by category, and insider
transaction data using the Finnhub REST API.  Output formats mirror the
Alpha Vantage news equivalents for consistent agent-facing data.
"""

import logging
from datetime import datetime
from typing import Literal

from .finnhub_common import (

    FinnhubError,
    ThirdPartyTimeoutError,
    _make_api_request,
    _now_str,
    _to_unix_timestamp,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

NewsCategory = Literal["general", "forex", "crypto", "merger"]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _format_unix_ts(ts: int | None) -> str:
    """Convert a Unix timestamp to a human-readable datetime string.

    Args:
        ts: Unix timestamp (seconds since epoch), or None.

    Returns:
        Formatted string like "2024-03-15 13:00:00", or "N/A" for None/zero.
    """
    if not ts:
        return "N/A"
    try:
        return datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M:%S")
    except (OSError, OverflowError, ValueError):
        return str(ts)


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def _fetch_company_news_data(symbol: str, params: dict) -> list[dict]:
    """Helper to fetch company news and handle errors by returning an empty list."""
    try:
        response = _make_api_request("company-news", params)
    except ThirdPartyTimeoutError:
        raise
    except Exception as e:
        logger.error(f"Error fetching company news for {symbol}: {e}")
        return []

    if not isinstance(response, list):
        return []

    return response

def get_company_news(symbol: str, start_date: str, end_date: str) -> str:
    """Fetch company-specific news via Finnhub /company-news.

    Returns a formatted markdown string with recent news for the given ticker,
    mirroring the output format of Alpha Vantage NEWS_SENTIMENT.

    Args:
        symbol: Equity ticker symbol (e.g. "AAPL").
        start_date: Inclusive start date in YYYY-MM-DD format.
        end_date: Inclusive end date in YYYY-MM-DD format.

    Returns:
        Formatted markdown string with article headlines, sources, summaries,
        and datetimes.

    Raises:
        FinnhubError: On API-level errors.
    """
    params = {
        "symbol": symbol,
        "from": start_date,
        "to": end_date,
    }

    articles: list[dict] = _fetch_company_news_data(symbol, params)

    header = (
        f"# Company News: {symbol} ({start_date} to {end_date}) — Finnhub\n"
        f"# Data retrieved on: {_now_str()}\n\n"
    )

    if not articles:
        return header + f"_No news articles found for {symbol} in the specified date range._\n"

    lines: list[str] = [header]
    for article in articles:
        headline = article.get("headline", "No headline")
        source = article.get("source", "Unknown")
        summary = article.get("summary", "")
        url = article.get("url", "")
        datetime_unix: int = article.get("datetime", 0)
        category = article.get("category", "")
        sentiment = article.get("sentiment", None)

        published = _format_unix_ts(datetime_unix)

        lines.append(f"### {headline}")
        meta = f"**Source:** {source} | **Published:** {published}"
        if category:
            meta += f" | **Category:** {category}"
        if sentiment is not None:
            meta += f" | **Sentiment:** {sentiment}"
        lines.append(meta)

        if summary:
            lines.append(summary)
        if url:
            lines.append(f"**Link:** {url}")
        lines.append("")

    return "\n".join(lines)


def get_market_news(category: NewsCategory = "general") -> str:
    """Fetch broad market news via Finnhub /news.

    Returns a formatted markdown string with the latest news items for the
    requested category.

    Args:
        category: News category — one of ``'general'``, ``'forex'``,
            ``'crypto'``, or ``'merger'``.

    Returns:
        Formatted markdown string with news articles.

    Raises:
        ValueError: When an unsupported category is provided.
        FinnhubError: On API-level errors.
    """
    valid_categories: set[str] = {"general", "forex", "crypto", "merger"}
    if category not in valid_categories:
        raise ValueError(
            f"Invalid category '{category}'. Must be one of: {sorted(valid_categories)}"
        )

    articles: list[dict] = _make_api_request("news", {"category": category})

    header = (
        f"# Market News: {category.title()} — Finnhub\n"
        f"# Data retrieved on: {_now_str()}\n\n"
    )

    if not articles:
        return header + f"_No news articles found for category '{category}'._\n"

    lines: list[str] = [header]
    for article in articles:
        headline = article.get("headline", "No headline")
        source = article.get("source", "Unknown")
        summary = article.get("summary", "")
        url = article.get("url", "")
        datetime_unix: int = article.get("datetime", 0)

        published = _format_unix_ts(datetime_unix)

        lines.append(f"### {headline}")
        lines.append(f"**Source:** {source} | **Published:** {published}")
        if summary:
            lines.append(summary)
        if url:
            lines.append(f"**Link:** {url}")
        lines.append("")

    return "\n".join(lines)


def get_insider_transactions(symbol: str) -> str:
    """Fetch insider buy/sell transactions via Finnhub /stock/insider-transactions.

    Returns a formatted markdown table with recent insider trades by executives,
    directors, and major shareholders, mirroring the output pattern of the
    Alpha Vantage INSIDER_TRANSACTIONS endpoint.

    Args:
        symbol: Equity ticker symbol (e.g. "AAPL").

    Returns:
        Formatted markdown string with insider transaction details.

    Raises:
        FinnhubError: On API-level errors or empty response.
    """
    data = _make_api_request("stock/insider-transactions", {"symbol": symbol})

    transactions: list[dict] = data.get("data", [])

    header = (
        f"# Insider Transactions: {symbol} — Finnhub\n"
        f"# Data retrieved on: {_now_str()}\n\n"
    )

    if not transactions:
        return header + f"_No insider transactions found for {symbol}._\n"

    lines: list[str] = [header]
    lines.append("| Name | Transaction | Shares | Share Price | Value | Date | Filing Date |")
    lines.append("|------|-------------|--------|-------------|-------|------|-------------|")

    for txn in transactions:
        name = txn.get("name", "N/A")
        transaction_code = txn.get("transactionCode", "")
        # Map Finnhub transaction codes to human-readable labels
        # P = Purchase, S = Sale, A = Award/Grant
        code_label_map = {
            "P": "Buy",
            "S": "Sell",
            "A": "Award/Grant",
            "D": "Disposition",
            "M": "Option Exercise",
            "G": "Gift",
            "F": "Tax Withholding",
            "X": "Option Exercise",
            "C": "Conversion",
        }
        txn_label = code_label_map.get(transaction_code, transaction_code or "N/A")

        raw_shares = txn.get("share", None)
        try:
            shares_str = f"{int(float(raw_shares)):,}" if raw_shares is not None else "N/A"
        except (ValueError, TypeError):
            shares_str = str(raw_shares)

        raw_price = txn.get("price", None)
        try:
            price_str = f"${float(raw_price):.2f}" if raw_price is not None else "N/A"
        except (ValueError, TypeError):
            price_str = str(raw_price)

        raw_value = txn.get("value", None)
        try:
            value_str = f"${float(raw_value):,.0f}" if raw_value is not None else "N/A"
        except (ValueError, TypeError):
            value_str = str(raw_value)

        txn_date = txn.get("transactionDate", "N/A")
        filing_date = txn.get("filingDate", "N/A")

        lines.append(
            f"| {name} | {txn_label} | {shares_str} | {price_str} | "
            f"{value_str} | {txn_date} | {filing_date} |"
        )

    return "\n".join(lines)
