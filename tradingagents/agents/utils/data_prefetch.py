"""
Pre-fetches data for analyst nodes so they don't depend on LLM tool calling.

This module calls the same underlying data functions that the tools use,
but invokes them directly. The fetched data is injected into the analyst
prompt so the LLM can analyze it in a single pass.

This approach works with all backends, including proxies that don't
support OpenAI-style tool calling (e.g., claude-max-api-proxy).
"""

from datetime import datetime, timedelta
from tradingagents.dataflows.interface import route_to_vendor


def prefetch_market_data(ticker: str, trade_date: str) -> dict:
    """Pre-fetch stock data and technical indicators for the market analyst.

    Returns a dict with 'stock_data' and 'indicators' keys.
    """
    results = {}

    # Fetch stock data for the past 30 days
    end_date = trade_date
    start_dt = datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=30)
    start_date = start_dt.strftime("%Y-%m-%d")

    try:
        results["stock_data"] = route_to_vendor(
            "get_stock_data", ticker, start_date, end_date
        )
    except Exception as e:
        results["stock_data"] = f"Error fetching stock data: {e}"

    # Fetch key technical indicators
    default_indicators = [
        "rsi", "macd", "macdh", "macds",
        "boll", "boll_ub", "boll_lb",
        "close_50_sma", "close_200_sma",
        "close_10_ema", "atr", "vwma",
    ]
    indicator_results = {}
    for indicator in default_indicators:
        try:
            value = route_to_vendor(
                "get_indicators", ticker, indicator, trade_date, 14
            )
            indicator_results[indicator] = value
        except Exception as e:
            indicator_results[indicator] = f"Error: {e}"
    results["indicators"] = indicator_results

    return results


def prefetch_news_data(ticker: str, trade_date: str) -> dict:
    """Pre-fetch news data for the news analyst.

    Returns a dict with 'ticker_news' and 'global_news' keys.
    """
    results = {}
    start_dt = datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=7)
    start_date = start_dt.strftime("%Y-%m-%d")

    try:
        results["ticker_news"] = route_to_vendor(
            "get_news", ticker, start_date, trade_date
        )
    except Exception as e:
        results["ticker_news"] = f"Error fetching news: {e}"

    try:
        results["global_news"] = route_to_vendor(
            "get_global_news", trade_date, 7, 10
        )
    except Exception as e:
        results["global_news"] = f"Error fetching global news: {e}"

    return results


def prefetch_social_data(ticker: str, trade_date: str) -> dict:
    """Pre-fetch data for the social media analyst.

    Returns a dict with 'ticker_news' key.
    """
    results = {}
    start_dt = datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=7)
    start_date = start_dt.strftime("%Y-%m-%d")

    try:
        results["ticker_news"] = route_to_vendor(
            "get_news", ticker, start_date, trade_date
        )
    except Exception as e:
        results["ticker_news"] = f"Error fetching news: {e}"

    return results


def prefetch_fundamentals_data(ticker: str, trade_date: str) -> dict:
    """Pre-fetch fundamental data for the fundamentals analyst.

    Returns a dict with keys for each financial data type.
    """
    results = {}

    try:
        results["fundamentals"] = route_to_vendor(
            "get_fundamentals", ticker, trade_date
        )
    except Exception as e:
        results["fundamentals"] = f"Error fetching fundamentals: {e}"

    try:
        results["balance_sheet"] = route_to_vendor(
            "get_balance_sheet", ticker, "quarterly", trade_date
        )
    except Exception as e:
        results["balance_sheet"] = f"Error fetching balance sheet: {e}"

    try:
        results["cashflow"] = route_to_vendor(
            "get_cashflow", ticker, "quarterly", trade_date
        )
    except Exception as e:
        results["cashflow"] = f"Error fetching cashflow: {e}"

    try:
        results["income_statement"] = route_to_vendor(
            "get_income_statement", ticker, "quarterly", trade_date
        )
    except Exception as e:
        results["income_statement"] = f"Error fetching income statement: {e}"

    return results


def format_market_context(data: dict) -> str:
    """Format pre-fetched market data into a context string for the LLM."""
    parts = []

    if data.get("stock_data"):
        parts.append(f"## Stock Price Data (OHLCV)\n{data['stock_data']}")

    if data.get("indicators"):
        parts.append("## Technical Indicators")
        for indicator, value in data["indicators"].items():
            parts.append(f"### {indicator}\n{value}")

    return "\n\n".join(parts)


def format_news_context(data: dict) -> str:
    """Format pre-fetched news data into a context string for the LLM."""
    parts = []

    if data.get("ticker_news"):
        parts.append(f"## Company-Specific News\n{data['ticker_news']}")

    if data.get("global_news"):
        parts.append(f"## Global Market News\n{data['global_news']}")

    return "\n\n".join(parts)


def format_social_context(data: dict) -> str:
    """Format pre-fetched social data into a context string for the LLM."""
    parts = []

    if data.get("ticker_news"):
        parts.append(
            f"## Company News & Social Media Discussions\n{data['ticker_news']}"
        )

    return "\n\n".join(parts)


def format_fundamentals_context(data: dict) -> str:
    """Format pre-fetched fundamentals data into a context string for the LLM."""
    parts = []

    if data.get("fundamentals"):
        parts.append(f"## Company Fundamentals Overview\n{data['fundamentals']}")

    if data.get("balance_sheet"):
        parts.append(f"## Balance Sheet\n{data['balance_sheet']}")

    if data.get("cashflow"):
        parts.append(f"## Cash Flow Statement\n{data['cashflow']}")

    if data.get("income_statement"):
        parts.append(f"## Income Statement\n{data['income_statement']}")

    return "\n\n".join(parts)
