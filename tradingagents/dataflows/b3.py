"""B3 (Brazilian Stock Exchange) dataflow module.
Wraps yfinance with B3-specific normalization and defaults.
"""

import re
from typing import Annotated
from .y_finance import (
    get_YFin_data_online,
    get_stock_stats_indicators_window,
    get_fundamentals as get_yfinance_fundamentals,
    get_balance_sheet as get_yfinance_balance_sheet,
    get_cashflow as get_yfinance_cashflow,
    get_income_statement as get_yfinance_income_statement,
    get_insider_transactions as get_yfinance_insider_transactions,
)
from .yfinance_news import get_news_yfinance, get_global_news_yfinance

def normalize_b3_ticker(ticker: str) -> str:
    """
    Append .SA to B3 tickers if missing.
    B3 tickers usually have 4 letters followed by 1-2 digits.
    Example: PETR4 -> PETR4.SA, VALE3 -> VALE3.SA, BOVA11 -> BOVA11.SA
    """
    ticker = ticker.upper().strip()
    # Pattern: 4 letters followed by 1 or 2 digits (e.g., 3, 4, 11) and optional F for fractional
    if re.match(r'^[A-Z]{4}[0-9]{1,2}F?$', ticker) and not ticker.endswith('.SA'):
        return f"{ticker}.SA"
    return ticker

def get_stock_data(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
):
    return get_YFin_data_online(normalize_b3_ticker(symbol), start_date, end_date)

def get_indicators(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "technical indicator to get"],
    curr_date: Annotated[str, "current date"],
    look_back_days: Annotated[int, "look back days"],
):
    return get_stock_stats_indicators_window(normalize_b3_ticker(symbol), indicator, curr_date, look_back_days)

def get_fundamentals(ticker, curr_date=None):
    return get_yfinance_fundamentals(normalize_b3_ticker(ticker), curr_date)

def get_balance_sheet(ticker, freq="quarterly", curr_date=None):
    return get_yfinance_balance_sheet(normalize_b3_ticker(ticker), freq, curr_date)

def get_cashflow(ticker, freq="quarterly", curr_date=None):
    return get_yfinance_cashflow(normalize_b3_ticker(ticker), freq, curr_date)

def get_income_statement(ticker, freq="quarterly", curr_date=None):
    return get_yfinance_income_statement(normalize_b3_ticker(ticker), freq, curr_date)

def get_news(ticker, start_date, end_date):
    return get_news_yfinance(normalize_b3_ticker(ticker), start_date, end_date)

def get_global_news(curr_date, look_back_days=7, limit=10):
    # For B3, we might want to add some Brazilian macro search terms
    # But for now, let's just use the default yfinance global news
    return get_global_news_yfinance(curr_date, look_back_days, limit)

def get_insider_transactions(ticker):
    return get_yfinance_insider_transactions(normalize_b3_ticker(ticker))
