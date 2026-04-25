"""yfinance vendor implementation for TradingAgents data layer.

Covers: OHLCV, technical indicators (via stockstats), fundamentals,
balance sheet, cash flow, income statement, news, insider transactions.
"""

from __future__ import annotations

import logging
import time

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


def get_news(ticker: str, curr_date: str = None) -> str:
    """Retrieve recent news articles using yfinance."""
    yf_sym = _to_yfinance_symbol(ticker)
    t = yf.Ticker(yf_sym)
    time.sleep(_REQUEST_DELAY)

    try:
        news = t.news
    except Exception as e:
        return f"Failed to retrieve news for '{ticker}': {e}"

    if not news:
        return f"No recent news available for '{ticker}'."

    lines = [f"# Recent News: {ticker}\n"]
    for i, item in enumerate(news[:20], 1):
        content = item.get("content", {})
        title = content.get("title") or item.get("title", "No Title")
        provider = content.get("provider", {})
        publisher = provider.get("displayName") if isinstance(provider, dict) else item.get("publisher", "Unknown")
        pub_date = content.get("pubDate", "")
        canonical = content.get("canonicalUrl", {})
        url = canonical.get("url") if isinstance(canonical, dict) else item.get("link", "")
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
