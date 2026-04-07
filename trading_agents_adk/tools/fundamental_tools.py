"""Fundamental analysis tools for the Fundamentals Analyst agent.

Plain Python functions that ADK wraps as FunctionTools.
"""

import json

try:
    import yfinance as yf
except ImportError:
    yf = None


def get_fundamentals(symbol: str) -> str:
    """Retrieve comprehensive fundamental data for a company.

    Args:
        symbol: Ticker symbol of the company, e.g. AAPL, NVDA

    Returns:
        A formatted string containing company info, key ratios,
        and financial metrics.
    """
    if yf is None:
        return f"[Mock] Fundamentals for {symbol}: PE=25, MarketCap=$2T, Revenue=$100B"

    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info

        key_fields = [
            "shortName", "sector", "industry", "marketCap", "enterpriseValue",
            "trailingPE", "forwardPE", "priceToBook", "profitMargins",
            "returnOnEquity", "returnOnAssets", "revenueGrowth",
            "earningsGrowth", "debtToEquity", "currentRatio",
            "totalRevenue", "grossMargins", "operatingMargins",
            "dividendYield", "beta", "fiftyTwoWeekHigh", "fiftyTwoWeekLow",
        ]

        lines = [f"Fundamentals for {symbol}:"]
        for field in key_fields:
            if field in info and info[field] is not None:
                value = info[field]
                if isinstance(value, (int, float)) and abs(value) > 1_000_000:
                    value = f"${value:,.0f}"
                elif isinstance(value, float):
                    value = f"{value:.4f}"
                lines.append(f"  {field}: {value}")

        return "\n".join(lines) if len(lines) > 1 else f"No fundamental data found for {symbol}"
    except Exception as e:
        return f"Error fetching fundamentals for {symbol}: {e}"


def get_balance_sheet(symbol: str) -> str:
    """Retrieve the balance sheet for a company.

    Args:
        symbol: Ticker symbol of the company

    Returns:
        A formatted string containing the most recent balance sheet data.
    """
    if yf is None:
        return f"[Mock] Balance sheet for {symbol}: TotalAssets=$300B, TotalDebt=$100B"

    try:
        ticker = yf.Ticker(symbol)
        bs = ticker.balance_sheet
        if bs.empty:
            return f"No balance sheet data found for {symbol}"
        latest = bs.iloc[:, 0]
        lines = [f"Balance Sheet for {symbol} (latest period):"]
        for idx, val in latest.items():
            if val is not None and str(val) != "nan":
                lines.append(f"  {idx}: {val:,.0f}" if isinstance(val, (int, float)) else f"  {idx}: {val}")
        return "\n".join(lines[:30])
    except Exception as e:
        return f"Error fetching balance sheet for {symbol}: {e}"


def get_income_statement(symbol: str) -> str:
    """Retrieve the income statement for a company.

    Args:
        symbol: Ticker symbol of the company

    Returns:
        A formatted string containing the most recent income statement.
    """
    if yf is None:
        return f"[Mock] Income statement for {symbol}: Revenue=$100B, NetIncome=$20B"

    try:
        ticker = yf.Ticker(symbol)
        inc = ticker.income_stmt
        if inc.empty:
            return f"No income statement data found for {symbol}"
        latest = inc.iloc[:, 0]
        lines = [f"Income Statement for {symbol} (latest period):"]
        for idx, val in latest.items():
            if val is not None and str(val) != "nan":
                lines.append(f"  {idx}: {val:,.0f}" if isinstance(val, (int, float)) else f"  {idx}: {val}")
        return "\n".join(lines[:30])
    except Exception as e:
        return f"Error fetching income statement for {symbol}: {e}"
