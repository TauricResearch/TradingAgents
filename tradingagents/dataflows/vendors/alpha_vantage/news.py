
import json

import pandas as pd

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.date_window import withhold_undisclosed_trades
from tradingagents.dataflows.vendors.alpha_vantage.common import (
    _make_api_request,
    format_datetime_for_api,
)


def get_news(ticker, start_date, end_date) -> dict[str, str] | str:
    """Returns live and historical market news & sentiment data from premier news outlets worldwide.

    Covers stocks, cryptocurrencies, forex, and topics like fiscal policy, mergers & acquisitions, IPOs.

    Args:
        ticker: Stock symbol for news articles.
        start_date: Start date for news search.
        end_date: End date for news search.

    Returns:
        Dictionary containing news sentiment data or JSON string.
    """

    # Without a limit the endpoint returns 50 articles, each with per-ticker
    # sentiment arrays, and all of it reaches the prompt.
    params = {
        "tickers": ticker,
        "time_from": format_datetime_for_api(start_date),
        "time_to": format_datetime_for_api(end_date, end_of_day=True),
        "limit": str(get_config()["news_article_limit"]),
    }

    return _make_api_request("NEWS_SENTIMENT", params)


def get_global_news(as_of_date, look_back_days: int | None = None, limit: int | None = None) -> dict[str, str] | str:
    """Returns global market news & sentiment data without ticker-specific filtering.

    Covers broad market topics like financial markets, economy, and more.

    Args:
        as_of_date: Current date in yyyy-mm-dd format.
        look_back_days: Number of days to look back; ``None`` uses
            ``global_news_lookback_days`` from the active config.
        limit: Maximum number of articles; ``None`` uses
            ``global_news_article_limit`` from the active config.

    Returns:
        Dictionary containing global news sentiment data or JSON string.
    """
    from datetime import datetime, timedelta

    config = get_config()
    if look_back_days is None:
        look_back_days = config["global_news_lookback_days"]
    if limit is None:
        limit = config["global_news_article_limit"]

    curr_dt = datetime.strptime(as_of_date, "%Y-%m-%d")
    start_dt = curr_dt - timedelta(days=look_back_days)
    start_date = start_dt.strftime("%Y-%m-%d")

    params = {
        "topics": "financial_markets,economy_macro,economy_monetary",
        "time_from": format_datetime_for_api(start_date),
        "time_to": format_datetime_for_api(as_of_date, end_of_day=True),
        "limit": str(limit),
    }

    return _make_api_request("NEWS_SENTIMENT", params)


def get_insider_transactions(symbol: str, as_of_date: str | None = None) -> str:
    """Returns the most recent insider transactions by key stakeholders.

    Covers transactions by founders, executives, board members, etc.

    Args:
        symbol: Ticker symbol. Example: "IBM".
        as_of_date: The analysis date (yyyy-mm-dd); a past one withholds them.

    Returns:
        CSV of up to ``insider_transaction_limit`` trades, newest first.
    """

    withheld = withhold_undisclosed_trades(as_of_date, symbol)
    if withheld:
        return withheld
    body = _make_api_request("INSIDER_TRANSACTIONS", {"symbol": symbol})

    # The endpoint takes no limit and returns every trade on record as JSON, which
    # for a long-listed company runs to hundreds of thousands of tokens (#1625).
    # Keep the most recent trades and serve them as CSV, as the Yahoo path does.
    try:
        trades = json.loads(body).get("data")
    except (json.JSONDecodeError, AttributeError):
        return body
    if not isinstance(trades, list):
        return body
    if not trades:
        return f"No insider transactions reported for symbol '{symbol}'"

    limit = get_config()["insider_transaction_limit"]
    trades = sorted(trades, key=lambda t: t.get("transaction_date") or "", reverse=True)
    kept = trades[:limit]
    header = f"# Insider Transactions data for {symbol}\n"
    if len(kept) < len(trades):
        header += f"# The {len(kept)} most recent of {len(trades)} trades\n"
    return header + pd.DataFrame(kept).to_csv(index=False)
