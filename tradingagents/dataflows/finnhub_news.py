"""Finnhub data provider for news and insider data."""

import os
from datetime import datetime

from dateutil.relativedelta import relativedelta


def _get_client():
    """Lazily create the Finnhub client."""
    import finnhub
    return finnhub.Client(api_key=os.environ.get("FINNHUB_API_KEY", ""))


def get_news(
    ticker: str,
    start_date: str,
    end_date: str,
) -> str:
    """Retrieve company news from Finnhub for a date range."""
    result = _get_client().company_news(ticker, _from=start_date, to=end_date)

    if not result:
        return ""

    news_entries = []
    for entry in result:
        timestamp = entry.get("datetime", 0)
        date_str = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d") if timestamp else "Unknown Date"
        headline = entry.get("headline", "No headline")
        summary = entry.get("summary", "No summary")
        news_entries.append(f"### {headline} ({date_str})\n{summary}")

    return f"## {ticker} News, from {start_date} to {end_date}:\n" + "\n\n".join(news_entries)


def get_global_news(
    curr_date: str,
    look_back_days: int = 7,
    limit: int = 5,
) -> str:
    """Retrieve general market news from Finnhub."""
    result = _get_client().general_news("general", min_id=0)

    if not result:
        return ""

    news_entries = []
    for entry in result[:limit]:
        timestamp = entry.get("datetime", 0)
        date_str = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d") if timestamp else "Unknown Date"
        headline = entry.get("headline", "No headline")
        summary = entry.get("summary", "No summary")
        news_entries.append(f"### {headline} ({date_str})\n{summary}")

    return "## General Market News:\n" + "\n\n".join(news_entries)


def get_insider_transactions(
    symbol: str,
) -> str:
    """Retrieve insider transactions from Finnhub (last 90 days)."""
    curr_dt = datetime.now()
    before_str = (curr_dt - relativedelta(days=90)).strftime("%Y-%m-%d")
    curr_str = curr_dt.strftime("%Y-%m-%d")

    data = _get_client().stock_insider_transactions(symbol, before_str, curr_str)

    if not data or "data" not in data or not data["data"]:
        return ""

    result_str = ""
    seen = []
    for entry in data["data"]:
        if entry not in seen:
            result_str += (
                f"### Filing Date: {entry['filingDate']}, {entry['name']}:\n"
                f"Change: {entry['change']}\n"
                f"Shares: {entry['share']}\n"
                f"Transaction Price: {entry['transactionPrice']}\n"
                f"Transaction Code: {entry['transactionCode']}\n\n"
            )
            seen.append(entry)

    return (
        f"## {symbol} insider transactions from {before_str} to {curr_str}:\n"
        + result_str
        + "The change field reflects the variation in share count—a negative number indicates a reduction in holdings. "
        "The transactionCode (e.g., S for sale) clarifies the nature of the transaction."
    )
