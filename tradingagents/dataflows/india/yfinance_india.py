"""India-aware wrappers around existing yfinance dataflows."""

from __future__ import annotations

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.india.quality import DataQuality, render_data_quality_block
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


def _with_quality(
    payload: object,
    *,
    source: str,
    symbol: str,
    coverage: str,
    warnings: list[str] | None = None,
) -> str:
    quality = DataQuality.current(
        source,
        coverage=coverage,
        confidence="medium",
        warnings=warnings
        or [
            "Yahoo Finance is a third-party fallback source; verify material figures against NSE/BSE/company filings.",
        ],
    )
    return f"{payload}\n\n{render_data_quality_block(quality)}\nSymbol: {symbol}"


def get_india_stock_data(symbol: str, start_date: str, end_date: str) -> str:
    normalized = _symbol(symbol)
    return _with_quality(
        get_YFin_data_online(normalized, start_date, end_date),
        source="yfinance_india",
        symbol=normalized,
        coverage=f"OHLCV {start_date} to {end_date}",
    )


def get_india_indicator(symbol: str, indicator: str, curr_date: str, look_back_days: int = 30) -> str:
    normalized = _symbol(symbol)
    return _with_quality(
        get_stock_stats_indicators_window(normalized, indicator, curr_date, look_back_days),
        source="yfinance_india",
        symbol=normalized,
        coverage=f"{indicator} window ending {curr_date}; look-back days {look_back_days}",
    )


def get_india_fundamentals(ticker: str, curr_date: str) -> str:
    normalized = _symbol(ticker)
    return _with_quality(
        get_yfinance_fundamentals(normalized, curr_date),
        source="yfinance_india",
        symbol=normalized,
        coverage=f"fundamentals as of {curr_date}",
    )


def get_india_balance_sheet(ticker: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
    normalized = _symbol(ticker)
    return _with_quality(
        get_yfinance_balance_sheet(normalized, freq, curr_date),
        source="yfinance_india",
        symbol=normalized,
        coverage=f"{freq} balance sheet as of {curr_date or 'latest available'}",
    )


def get_india_cashflow(ticker: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
    normalized = _symbol(ticker)
    return _with_quality(
        get_yfinance_cashflow(normalized, freq, curr_date),
        source="yfinance_india",
        symbol=normalized,
        coverage=f"{freq} cash flow as of {curr_date or 'latest available'}",
    )


def get_india_income_statement(ticker: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
    normalized = _symbol(ticker)
    return _with_quality(
        get_yfinance_income_statement(normalized, freq, curr_date),
        source="yfinance_india",
        symbol=normalized,
        coverage=f"{freq} income statement as of {curr_date or 'latest available'}",
    )


def get_india_news(ticker: str, start_date: str, end_date: str) -> str:
    normalized = _symbol(ticker)
    return _with_quality(
        get_news_yfinance(normalized, start_date, end_date),
        source="yfinance_news_india",
        symbol=normalized,
        coverage=f"news {start_date} to {end_date}",
    )


def get_india_global_news(curr_date: str, look_back_days: int | None = None, limit: int | None = None) -> str:
    return _with_quality(
        get_global_news_yfinance(curr_date, look_back_days, limit),
        source="yfinance_news_india",
        symbol="INDIA_MACRO_NEWS",
        coverage=f"global/India macro news ending {curr_date}; look-back days {look_back_days}; limit {limit}",
    )


def get_india_insider_transactions(ticker: str) -> str:
    normalized = _symbol(ticker)
    return _with_quality(
        get_yfinance_insider_transactions(normalized),
        source="yfinance_india",
        symbol=normalized,
        coverage="insider transactions if available",
    )
