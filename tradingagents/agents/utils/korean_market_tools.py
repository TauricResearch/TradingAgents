"""LangChain tool definitions for Korean market data.

These tools wrap the Korean data sources (FinanceDataReader, Naver, DART, pykrx)
and are used by agents through the vendor routing system.
"""

from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor


# ── Korean Stock Data Tools ──────────────────────────────────────────────────

@tool
def get_krx_stock_data(
    symbol: Annotated[str, "KRX ticker symbol (e.g., '005930' for Samsung, '000660' for SK Hynix)"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """
    Retrieve KRX (Korea Exchange) stock OHLCV price data.
    For Korean stocks listed on KOSPI/KOSDAQ.
    Args:
        symbol (str): KRX ticker code (6-digit, e.g., '005930')
        start_date (str): Start date in yyyy-mm-dd format
        end_date (str): End date in yyyy-mm-dd format
    Returns:
        str: Formatted stock price data in KRW
    """
    return route_to_vendor("get_krx_stock_data", symbol, start_date, end_date)


@tool
def get_krx_indicators(
    symbol: Annotated[str, "KRX ticker symbol (e.g., '005930')"],
    indicator: Annotated[str, "Technical indicator (e.g., 'rsi', 'macd', 'close_50_sma')"],
    curr_date: Annotated[str, "Current trading date in YYYY-mm-dd format"],
    look_back_days: Annotated[int, "How many days to look back"] = 30,
) -> str:
    """
    Calculate technical indicators for KRX-listed stocks.
    Supported indicators: close_50_sma, close_200_sma, close_10_ema, macd, macds, macdh,
    rsi, boll, boll_ub, boll_lb, atr, vwma, mfi
    Args:
        symbol (str): KRX ticker code
        indicator (str): Technical indicator name
        curr_date (str): Current trading date
        look_back_days (int): Look-back period (default 30)
    Returns:
        str: Indicator values over the look-back period
    """
    return route_to_vendor("get_krx_indicators", symbol, indicator, curr_date, look_back_days)


# ── Korean Market Context Tools ──────────────────────────────────────────────

@tool
def get_exchange_rate(
    currency_pair: Annotated[str, "Currency pair (e.g., 'USD/KRW', 'JPY/KRW', 'EUR/KRW', 'CNY/KRW')"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """
    Retrieve exchange rate data. Essential for Korean market analysis
    as USD/KRW rate significantly impacts Korean stocks (especially export companies).
    Args:
        currency_pair (str): Currency pair (e.g., 'USD/KRW')
        start_date (str): Start date
        end_date (str): End date
    Returns:
        str: Exchange rate time series data
    """
    return route_to_vendor("get_exchange_rate", currency_pair, start_date, end_date)


@tool
def get_korea_index(
    index_code: Annotated[str, "Index code: 'KS11' (KOSPI), 'KQ11' (KOSDAQ), 'KS200' (KOSPI200)"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """
    Retrieve Korean market index data (KOSPI, KOSDAQ, KOSPI200).
    Critical for understanding overall Korean market trend and sector rotation.
    Args:
        index_code (str): 'KS11' for KOSPI, 'KQ11' for KOSDAQ, 'KS200' for KOSPI200
        start_date (str): Start date
        end_date (str): End date
    Returns:
        str: Index OHLCV data
    """
    return route_to_vendor("get_korea_index", index_code, start_date, end_date)


@tool
def get_investor_trading(
    symbol: Annotated[str, "KRX ticker symbol (e.g., '005930')"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """
    Retrieve foreign and institutional investor trading data (수급 데이터).
    Shows net buying/selling by investor type: foreigners (외국인), institutions (기관),
    individuals (개인), pension funds (연기금), etc.
    This is one of the MOST IMPORTANT indicators for Korean stocks.
    Args:
        symbol (str): KRX ticker code
        start_date (str): Start date
        end_date (str): End date
    Returns:
        str: Investor flow data with net buy/sell amounts in KRW
    """
    return route_to_vendor("get_investor_trading", symbol, start_date, end_date)


# ── Korean Fundamentals (KRX + DART) ────────────────────────────────────────

@tool
def get_krx_fundamentals(
    ticker: Annotated[str, "KRX ticker symbol (e.g., '005930')"],
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
) -> str:
    """
    Retrieve fundamental data for a KRX-listed company.
    Includes PER, PBR, EPS, BPS, dividend yield, market cap from KRX data.
    Args:
        ticker (str): KRX ticker code
        curr_date (str): Current date
    Returns:
        str: Company fundamental ratios and market cap info
    """
    return route_to_vendor("get_krx_fundamentals", ticker, curr_date)


@tool
def get_dart_financials(
    ticker: Annotated[str, "KRX ticker symbol (e.g., '005930')"],
    year: Annotated[str, "Business year (e.g., '2024')"],
    report_code: Annotated[str, "Report code: '11013'=1Q, '11012'=반기, '11014'=3Q, '11011'=연간"] = "11011",
) -> str:
    """
    Retrieve detailed financial statements from DART (전자공시시스템).
    Includes balance sheet, income statement, and cash flow from official filings.
    Requires DART_API_KEY environment variable.
    Args:
        ticker (str): KRX ticker code
        year (str): Business year
        report_code (str): '11011' for annual, '11013' for Q1, '11012' for half-year, '11014' for Q3
    Returns:
        str: Detailed consolidated financial statements
    """
    return route_to_vendor("get_dart_financials", ticker, year, report_code)


@tool
def get_dart_disclosures(
    ticker: Annotated[str, "KRX ticker symbol (e.g., '005930')"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """
    Retrieve recent DART disclosures/filings (공시) for a Korean company.
    DART 공시 is the primary source of corporate events, regulatory filings,
    and material information for Korean stocks.
    Args:
        ticker (str): KRX ticker code
        start_date (str): Start date
        end_date (str): End date
    Returns:
        str: List of recent disclosures with filing dates and types
    """
    return route_to_vendor("get_dart_disclosures", ticker, start_date, end_date)


@tool
def get_dart_shareholders(
    ticker: Annotated[str, "KRX ticker symbol (e.g., '005930')"],
) -> str:
    """
    Retrieve major shareholder information (대주주 지분 현황) from DART.
    Shows ownership structure which is critical for Korean corporate governance analysis.
    Args:
        ticker (str): KRX ticker code
    Returns:
        str: Major shareholders with ownership percentages
    """
    return route_to_vendor("get_dart_shareholders", ticker)


# ── Korean News Tools ────────────────────────────────────────────────────────

@tool
def get_korean_news(
    ticker: Annotated[str, "KRX ticker symbol or company name (e.g., '005930' or '삼성전자')"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """
    Retrieve Korean financial news for a specific stock.
    Searches Korean news sources (Naver, Google News Korea) for company-specific news.
    Args:
        ticker (str): KRX ticker code or Korean company name
        start_date (str): Start date
        end_date (str): End date
    Returns:
        str: Korean financial news articles
    """
    return route_to_vendor("get_korean_news", ticker, start_date, end_date)


@tool
def get_korean_global_news(
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    look_back_days: Annotated[int, "Number of days to look back"] = 7,
    limit: Annotated[int, "Maximum number of articles to return"] = 10,
) -> str:
    """
    Retrieve Korean macro/global economic news.
    Covers: BOK base rate, KOSPI outlook, USD/KRW exchange rate,
    Korean economy, foreign investment trends.
    Args:
        curr_date (str): Current date
        look_back_days (int): Days to look back (default 7)
        limit (int): Max articles (default 10)
    Returns:
        str: Korean macro/economic news articles
    """
    return route_to_vendor("get_korean_global_news", curr_date, look_back_days, limit)
