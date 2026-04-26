"""yfinance vendor implementation for TradingAgents data layer.

Covers: OHLCV, technical indicators (via stockstats), fundamentals,
balance sheet, cash flow, income statement, news, global news, insider transactions.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

_CRYPTO_QUOTE_SUFFIXES = ("USDT", "USDC", "BUSD", "FDUSD", "TUSD", "BTC", "ETH", "BNB")
_REQUEST_DELAY = 0.5  # seconds between calls to avoid Yahoo Finance throttling


def _is_crypto(ticker: str) -> bool:
    t = ticker.upper()
    return "." not in t and any(t.endswith(s) for s in _CRYPTO_QUOTE_SUFFIXES)


def _to_yfinance_symbol(ticker: str) -> str:
    """Convert a Binance-style crypto ticker to yfinance format (BTCUSDT → BTC-USDT)."""
    if _is_crypto(ticker):
        t = ticker.upper()
        for suffix in sorted(_CRYPTO_QUOTE_SUFFIXES, key=len, reverse=True):
            if t.endswith(suffix):
                base = t[: -len(suffix)]
                return f"{base}-{suffix}"
    return ticker


def _history_to_df(ticker: str, start: str, end: str) -> pd.DataFrame:
    """Fetch yfinance history and return a normalised OHLCV DataFrame."""
    yf_sym = _to_yfinance_symbol(ticker)
    t = yf.Ticker(yf_sym)
    time.sleep(_REQUEST_DELAY)
    df = t.history(start=start, end=end, auto_adjust=True)
    if df.empty:
        return pd.DataFrame()
    df = df.reset_index()
    df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
    return df[["Date", "Open", "High", "Low", "Close", "Volume"]].copy()


def get_stock_data(symbol: str, start_date: str, end_date: str) -> str:
    """Retrieve OHLCV price data using yfinance.

    Args:
        symbol: Ticker (AAPL, CNC.TO, BTC-USD, BTCUSDT)
        start_date: YYYY-MM-DD
        end_date: YYYY-MM-DD

    Returns:
        CSV string with OHLCV data
    """
    df = _history_to_df(symbol, start_date, end_date)
    if df.empty:
        return f"No price data available for '{symbol}' from {start_date} to {end_date}."
    return df.set_index("Date").to_csv()


_INDICATOR_DESCRIPTIONS: dict[str, str] = {
    "close_34_sma": "34 SMA: Short-to-medium-term Fibonacci trend indicator.",
    "close_56_sma": "56 SMA: Medium-term trend indicator.",
    "close_89_sma": "89 SMA: Long-term Fibonacci trend benchmark.",
    "macd": "MACD: Momentum via EMA differences.",
    "macds": "MACD Signal: EMA smoothing of the MACD line.",
    "macdh": "MACD Histogram: Gap between MACD and its signal.",
    "rsi": "RSI: Momentum indicator for overbought/oversold conditions.",
    "boll": "Bollinger Middle: 20 SMA as basis for Bollinger Bands.",
    "boll_ub": "Bollinger Upper Band: 2 std deviations above middle.",
    "boll_lb": "Bollinger Lower Band: 2 std deviations below middle.",
    "atr": "ATR: Average True Range, measures volatility.",
    "vwma": "VWMA: Volume-weighted moving average.",
    "mfi": "MFI: Money Flow Index combining price and volume.",
}


def get_indicators(
    symbol: str,
    indicator: str,
    curr_date: str,
    look_back_days: int = 30,
) -> str:
    """Calculate a technical indicator using yfinance history + stockstats.

    Args:
        symbol: Ticker symbol
        indicator: stockstats indicator key (e.g. rsi, macd, close_34_sma)
        curr_date: Current trading date YYYY-MM-DD
        look_back_days: Calendar days to look back for the result window

    Returns:
        Formatted indicator values string
    """
    from datetime import datetime

    from dateutil.relativedelta import relativedelta
    from stockstats import wrap

    if indicator not in _INDICATOR_DESCRIPTIONS:
        raise ValueError(
            f"Indicator '{indicator}' is not supported. "
            f"Choose from: {list(_INDICATOR_DESCRIPTIONS.keys())}"
        )

    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    before_dt = curr_dt - relativedelta(days=look_back_days)
    fetch_start = curr_dt - relativedelta(years=1)

    df = _history_to_df(symbol, fetch_start.strftime("%Y-%m-%d"), curr_date)
    if df.empty:
        return f"No data available for '{symbol}' up to {curr_date}."

    from .stockstats_utils import _clean_dataframe
    df = _clean_dataframe(df)
    df = wrap(df)
    df["Date"] = df["Date"].dt.strftime("%Y-%m-%d") if hasattr(df["Date"].iloc[0], "strftime") else df["Date"]
    df[indicator]  # trigger stockstats calculation

    date_map: dict[str, str] = {
        row["Date"]: str(row[indicator]) if not pd.isna(row[indicator]) else "N/A"
        for _, row in df.iterrows()
    }

    lines: list[str] = []
    cur = curr_dt
    while cur >= before_dt:
        date_str = cur.strftime("%Y-%m-%d")
        value = date_map.get(date_str, "N/A: Not a trading day")
        lines.append(f"{date_str}: {value}")
        cur -= relativedelta(days=1)

    description = _INDICATOR_DESCRIPTIONS[indicator]
    return (
        f"## {indicator} values from {before_dt.strftime('%Y-%m-%d')} to {curr_date}:\n\n"
        f"{description}\n\n"
        + "\n".join(lines)
    )


def get_fundamentals(ticker: str, curr_date: str = None) -> str:
    """Retrieve fundamental overview data using yfinance.

    Returns a clear "not available" message for crypto tickers.
    """
    if _is_crypto(ticker):
        return (
            f"Fundamental data is not available for crypto assets ({ticker}). "
            "Cryptocurrencies do not have company fundamentals such as earnings, "
            "balance sheets, or income statements."
        )

    yf_sym = _to_yfinance_symbol(ticker)
    t = yf.Ticker(yf_sym)
    time.sleep(_REQUEST_DELAY)
    info = t.info

    if not info or not info.get("quoteType"):
        return f"No fundamental data available for '{ticker}'."

    FIELDS = [
        ("Company", "longName"),
        ("Sector", "sector"),
        ("Industry", "industry"),
        ("Market Cap", "marketCap"),
        ("Enterprise Value", "enterpriseValue"),
        ("P/E Ratio (TTM)", "trailingPE"),
        ("Forward P/E", "forwardPE"),
        ("PEG Ratio", "pegRatio"),
        ("Price/Book", "priceToBook"),
        ("Price/Sales", "priceToSalesTrailing12Months"),
        ("EV/EBITDA", "enterpriseToEbitda"),
        ("EV/Revenue", "enterpriseToRevenue"),
        ("Revenue (TTM)", "totalRevenue"),
        ("Gross Profit", "grossProfits"),
        ("EBITDA", "ebitda"),
        ("Net Income", "netIncomeToCommon"),
        ("EPS (TTM)", "trailingEps"),
        ("Forward EPS", "forwardEps"),
        ("Revenue Growth", "revenueGrowth"),
        ("Earnings Growth", "earningsGrowth"),
        ("Gross Margin", "grossMargins"),
        ("Operating Margin", "operatingMargins"),
        ("Profit Margin", "profitMargins"),
        ("Return on Equity", "returnOnEquity"),
        ("Return on Assets", "returnOnAssets"),
        ("Debt/Equity", "debtToEquity"),
        ("Current Ratio", "currentRatio"),
        ("Quick Ratio", "quickRatio"),
        ("Beta", "beta"),
        ("52-Week High", "fiftyTwoWeekHigh"),
        ("52-Week Low", "fiftyTwoWeekLow"),
        ("Dividend Yield", "dividendYield"),
        ("Payout Ratio", "payoutRatio"),
        ("Short Ratio", "shortRatio"),
        ("Shares Outstanding", "sharesOutstanding"),
        ("Float Shares", "floatShares"),
        ("Analyst Target Price", "targetMeanPrice"),
        ("Analyst Recommendation", "recommendationKey"),
        ("Number of Analysts", "numberOfAnalystOpinions"),
        ("Country", "country"),
        ("Exchange", "exchange"),
        ("Currency", "currency"),
        ("Description", "longBusinessSummary"),
    ]

    lines = [f"# Fundamental Data: {ticker}"]
    for label, key in FIELDS:
        val = info.get(key)
        if val is not None:
            lines.append(f"**{label}**: {val}")

    return "\n".join(lines)


def get_balance_sheet(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
    """Retrieve balance sheet data using yfinance."""
    if _is_crypto(ticker):
        return f"Balance sheet data is not available for crypto assets ({ticker})."

    yf_sym = _to_yfinance_symbol(ticker)
    t = yf.Ticker(yf_sym)
    time.sleep(_REQUEST_DELAY)
    df = t.quarterly_balance_sheet if freq == "quarterly" else t.balance_sheet

    if df is None or df.empty:
        return f"No balance sheet data available for '{ticker}'."

    return f"# Balance Sheet ({freq.capitalize()}): {ticker}\n\n{df.to_string()}"


def get_cashflow(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
    """Retrieve cash flow statement data using yfinance."""
    if _is_crypto(ticker):
        return f"Cash flow data is not available for crypto assets ({ticker})."

    yf_sym = _to_yfinance_symbol(ticker)
    t = yf.Ticker(yf_sym)
    time.sleep(_REQUEST_DELAY)
    df = t.quarterly_cashflow if freq == "quarterly" else t.cashflow

    if df is None or df.empty:
        return f"No cash flow data available for '{ticker}'."

    return f"# Cash Flow Statement ({freq.capitalize()}): {ticker}\n\n{df.to_string()}"


def get_income_statement(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
    """Retrieve income statement data using yfinance."""
    if _is_crypto(ticker):
        return f"Income statement data is not available for crypto assets ({ticker})."

    yf_sym = _to_yfinance_symbol(ticker)
    t = yf.Ticker(yf_sym)
    time.sleep(_REQUEST_DELAY)
    df = t.quarterly_financials if freq == "quarterly" else t.financials

    if df is None or df.empty:
        return f"No income statement data available for '{ticker}'."

    return f"# Income Statement ({freq.capitalize()}): {ticker}\n\n{df.to_string()}"


# ---------------------------------------------------------------------------
# News helpers — defined before any public function that calls them
# ---------------------------------------------------------------------------

_GLOBAL_NEWS_INDICES: list[str] = ["^GSPC", "^DJI", "^IXIC"]
"""Major market indices used as proxy for global news (S&P 500, Dow Jones, NASDAQ)."""

_DEFAULT_NEWS_LIMIT: int = 20
"""Maximum articles returned by get_news when no explicit limit is supplied."""


def _fetch_index_news(index_symbol: str) -> list[dict]:
    """Fetch raw news article dicts for a single market index symbol."""
    t = yf.Ticker(index_symbol)
    time.sleep(_REQUEST_DELAY)
    news = t.news
    return news if news else []


def _deduplicate_articles(articles: list[dict]) -> list[dict]:
    """Remove duplicate articles by normalised title; preserves first-seen order."""
    seen: set[str] = set()
    unique: list[dict] = []
    for article in articles:
        content = article.get("content", {})
        title = content.get("title") or article.get("title", "")
        key = title.strip().lower()
        if key and key not in seen:
            seen.add(key)
            unique.append(article)
    return unique


def _article_datetime(article: dict) -> datetime:
    """Parse a news article dict to a timezone-naive UTC datetime.

    Tries `content.pubDate` (ISO 8601) first, then `providerPublishTime`
    (Unix timestamp). Returns `datetime.min` if neither is parseable so
    the article sorts to the bottom rather than raising.
    """
    content = article.get("content", {})
    pub_date_str: str = content.get("pubDate", "")
    if pub_date_str:
        try:
            return datetime.fromisoformat(
                pub_date_str.replace("Z", "+00:00")
            ).replace(tzinfo=None)
        except ValueError:
            pass
    ts = article.get("providerPublishTime")
    if ts:
        return datetime.utcfromtimestamp(ts)
    return datetime.min


def _filter_by_date_range(
    articles: list[dict],
    start_date: str,
    end_date: str,
) -> list[dict]:
    """Filter articles to [start_date, end_date] inclusive; sorts descending by date."""
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)

    filtered = [
        a for a in articles
        if start_dt <= _article_datetime(a) <= end_dt
    ]
    filtered.sort(key=_article_datetime, reverse=True)
    return filtered


def _format_news_markdown(articles: list[dict], header: str) -> str:
    """Format a list of news dicts into a numbered markdown document."""
    lines: list[str] = [f"# {header}\n"]

    for i, article in enumerate(articles, 1):
        content = article.get("content", {})
        title = content.get("title") or article.get("title", "No Title")
        provider = content.get("provider", {})
        publisher = (
            provider.get("displayName")
            if isinstance(provider, dict)
            else article.get("publisher", "Unknown")
        )
        pub_date = content.get("pubDate", "")
        canonical = content.get("canonicalUrl", {})
        url = (
            canonical.get("url")
            if isinstance(canonical, dict)
            else article.get("link", "")
        )
        summary = content.get("summary", "")

        lines.append(f"## {i}. {title}")
        if publisher:
            lines.append(f"**Publisher**: {publisher}")
        if pub_date:
            lines.append(f"**Date**: {pub_date}")
        if url:
            lines.append(f"**URL**: {url}")
        if summary:
            lines.append(f"**Summary**: {summary}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public news functions
# ---------------------------------------------------------------------------

def get_news(ticker: str, start_date: str, end_date: str) -> str:
    """Retrieve news articles for a ticker filtered to [start_date, end_date].

    Args:
        ticker: Ticker symbol (AAPL, BTCUSDT, etc.)
        start_date: Inclusive lower bound in YYYY-MM-DD format.
        end_date: Inclusive upper bound in YYYY-MM-DD format.

    Returns:
        Markdown-formatted string of news articles within the date range.
    """
    yf_sym = _to_yfinance_symbol(ticker)
    t = yf.Ticker(yf_sym)
    time.sleep(_REQUEST_DELAY)

    try:
        news = t.news
    except Exception as e:
        return f"Failed to retrieve news for '{ticker}': {e}"

    if not news:
        return f"No recent news available for '{ticker}'."

    filtered = _filter_by_date_range(news, start_date, end_date)

    if not filtered:
        return f"No news found for '{ticker}' between {start_date} and {end_date}."

    return _format_news_markdown(filtered[:_DEFAULT_NEWS_LIMIT], f"Recent News: {ticker}")


def get_global_news(
    curr_date: str,
    look_back_days: int = 7,
    limit: int = 50,
) -> str:
    """Retrieve global market news by aggregating from major indices.

    yfinance has no dedicated global news endpoint.
    Strategy: fetch from S&P 500, Dow Jones, NASDAQ composite,
    deduplicate by title, filter by date range, then format as markdown.

    Args:
        curr_date: Current date in YYYY-MM-DD format.
        look_back_days: Number of calendar days to look back.
        limit: Maximum number of articles to return.

    Returns:
        Markdown-formatted string of global news articles.

    Raises:
        RuntimeError: If all indices fail to return news (signals router to try next vendor).
    """
    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_dt = curr_dt - timedelta(days=look_back_days)
    start_str = start_dt.strftime("%Y-%m-%d")

    all_articles: list[dict] = []
    errors: list[str] = []

    for index in _GLOBAL_NEWS_INDICES:
        try:
            all_articles.extend(_fetch_index_news(index))
        except Exception as e:
            logger.warning("Failed to fetch news for index %s: %s", index, e)
            errors.append(f"{index}: {e}")

    # All indices failed → raise so router falls back to alpha_vantage
    if not all_articles and errors:
        raise RuntimeError(f"All index news fetches failed: {'; '.join(errors)}")

    if not all_articles:
        return "No global news available from market indices."

    filtered = _filter_by_date_range(
        _deduplicate_articles(all_articles), start_str, curr_date
    )

    if not filtered:
        return f"No global news found in range {start_str} to {curr_date}."

    return _format_news_markdown(filtered[:limit], "Global Market News")


def get_insider_transactions(ticker: str, curr_date: str = None) -> str:
    """Retrieve insider transactions and major holders using yfinance."""
    if _is_crypto(ticker):
        return f"Insider transaction data is not available for crypto assets ({ticker})."

    yf_sym = _to_yfinance_symbol(ticker)
    t = yf.Ticker(yf_sym)
    time.sleep(_REQUEST_DELAY)

    parts: list[str] = [f"# Insider Transactions & Holders: {ticker}\n"]

    try:
        insider_tx = t.insider_transactions
        if insider_tx is not None and not insider_tx.empty:
            parts.append("## Recent Insider Transactions")
            parts.append(insider_tx.to_string())
            parts.append("")
    except Exception as e:
        logger.warning("Could not fetch insider_transactions for %s: %s", ticker, e)

    try:
        major_holders = t.major_holders
        if major_holders is not None and not major_holders.empty:
            parts.append("## Major Holders")
            parts.append(major_holders.to_string())
            parts.append("")
    except Exception as e:
        logger.warning("Could not fetch major_holders for %s: %s", ticker, e)

    try:
        inst_holders = t.institutional_holders
        if inst_holders is not None and not inst_holders.empty:
            parts.append("## Institutional Holders (Top 10)")
            parts.append(inst_holders.head(10).to_string())
    except Exception as e:
        logger.warning("Could not fetch institutional_holders for %s: %s", ticker, e)

    if len(parts) == 1:
        return f"No insider transaction data available for '{ticker}'."

    return "\n".join(parts)
