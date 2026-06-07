"""India-aware wrappers around existing yfinance dataflows."""

from __future__ import annotations

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.india.symbols import validate_india_symbol_or_raise
from tradingagents.dataflows.y_finance import (
    get_YFin_data_online,
    get_balance_sheet as get_yfinance_balance_sheet,
    get_cashflow as get_yfinance_cashflow,
    get_fundamentals as get_yfinance_fundamentals,
    get_income_statement as get_yfinance_income_statement,
    get_insider_transactions as get_yfinance_insider_transactions,
    get_stock_stats_indicators_window,
)
from tradingagents.dataflows.yfinance_news import get_global_news_yfinance, get_news_yfinance


def _symbol(symbol: str) -> str:
    return validate_india_symbol_or_raise(symbol, get_config())


def get_india_stock_data(symbol: str, start_date: str, end_date: str) -> str:
    return get_YFin_data_online(_symbol(symbol), start_date, end_date)


def get_india_indicator(symbol: str, indicator: str, curr_date: str, look_back_days: int = 30) -> str:
    return get_stock_stats_indicators_window(_symbol(symbol), indicator, curr_date, look_back_days)


def get_india_fundamentals(ticker: str, curr_date: str) -> str:
    return get_yfinance_fundamentals(_symbol(ticker), curr_date)


def get_india_balance_sheet(ticker: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
    return get_yfinance_balance_sheet(_symbol(ticker), freq, curr_date)


def get_india_cashflow(ticker: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
    return get_yfinance_cashflow(_symbol(ticker), freq, curr_date)


def get_india_income_statement(ticker: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
    return get_yfinance_income_statement(_symbol(ticker), freq, curr_date)


def get_india_news(ticker: str, start_date: str, end_date: str) -> str:
    return get_news_yfinance(_symbol(ticker), start_date, end_date)


def get_india_global_news(curr_date: str, look_back_days: int | None = None, limit: int | None = None) -> str:
    return get_global_news_yfinance(curr_date, look_back_days, limit)


def get_india_insider_transactions(ticker: str) -> str:
    return get_yfinance_insider_transactions(_symbol(ticker))
