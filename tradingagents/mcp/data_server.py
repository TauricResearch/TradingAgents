"""TradingAgents data MCP server (stdio).

Exposes the framework's data layer as MCP tools so a Claude client (Claude
Code / Claude Desktop) can fetch market, news, fundamental, macro, and
prediction-market data. Each tool is a thin wrapper that calls the *existing*
``@tool`` implementations from
:mod:`tradingagents.agents.utils.agent_utils` via their underlying ``.func``
(single source of truth — same vendor routing, config, and formatting as the
native pipeline), so this server adds an interface but no data logic.

The server makes **no LLM calls**. Claude (the MCP client) performs all agent
reasoning, so running the whole multi-agent pipeline through this server costs
zero LLM API spend — only the (mostly free / keyless) data sources are hit.

Run with: ``tradingagents-data-mcp`` (installed script) or
``python -m tradingagents.mcp.data_server``.
"""

from __future__ import annotations

import logging

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Load .env (free data-source keys: FRED_API_KEY, ALPHA_VANTAGE_API_KEY, ...)
# before the config snapshot is taken, so vendors that need a key see it.
load_dotenv()

from tradingagents.agents.utils.agent_utils import (  # noqa: E402  (after load_dotenv)
    build_instrument_context,
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_global_news,
    get_income_statement,
    get_indicators,
    get_insider_transactions,
    get_macro_indicators,
    get_news,
    get_prediction_markets,
    get_stock_data,
    get_verified_market_snapshot,
    resolve_instrument_identity,
)
from tradingagents.dataflows.config import set_config  # noqa: E402
from tradingagents.dataflows.reddit import fetch_reddit_posts  # noqa: E402
from tradingagents.dataflows.stocktwits import fetch_stocktwits_messages  # noqa: E402
from tradingagents.default_config import DEFAULT_CONFIG  # noqa: E402
from tradingagents.mcp._returns import fetch_realized_return  # noqa: E402

logger = logging.getLogger(__name__)

# Initialise the dataflows config exactly like the CLI/graph do, so vendor
# routing (yfinance by default) and limits match the native pipeline. Honours
# TRADINGAGENTS_* env overrides baked into DEFAULT_CONFIG.
set_config(DEFAULT_CONFIG.copy())

mcp = FastMCP("tradingagents-data")


# --------------------------------------------------------------------------- #
# Market / price / technical tools
# --------------------------------------------------------------------------- #
@mcp.tool()
def get_stock_price_data(symbol: str, start_date: str, end_date: str) -> str:
    """Retrieve OHLCV stock price data for a ticker over a date range.

    Args:
        symbol: Ticker symbol, e.g. AAPL, 0700.HK, BTC-USD.
        start_date: Start date in yyyy-mm-dd format.
        end_date: End date in yyyy-mm-dd format.
    """
    return get_stock_data.func(symbol, start_date, end_date)


@mcp.tool()
def get_technical_indicators(
    symbol: str, indicator: str, curr_date: str, look_back_days: int = 30
) -> str:
    """Retrieve technical indicator(s) for a ticker (e.g. rsi, macd, boll, sma).

    Args:
        symbol: Ticker symbol, e.g. AAPL.
        indicator: Indicator name(s); a comma-separated list is allowed.
        curr_date: Current trading date in yyyy-mm-dd format.
        look_back_days: Trailing window length in days (default 30).
    """
    return get_indicators.func(symbol, indicator, curr_date, look_back_days)


@mcp.tool()
def get_market_snapshot(symbol: str, curr_date: str, look_back_days: int = 30) -> str:
    """Deterministic verification snapshot for exact market-data claims.

    Returns the latest OHLCV row on or before ``curr_date``, common indicators,
    and recent closes. Use this as the source of truth before asserting exact
    price levels, RSI/MACD, Bollinger bands, moving averages, or support/
    resistance.

    Args:
        symbol: Ticker symbol.
        curr_date: Current trading date in yyyy-mm-dd format.
        look_back_days: Recent trading rows to include for sanity-checking.
    """
    return get_verified_market_snapshot.func(symbol, curr_date, look_back_days)


# --------------------------------------------------------------------------- #
# News / macro / prediction-market tools
# --------------------------------------------------------------------------- #
@mcp.tool()
def get_ticker_news(ticker: str, start_date: str, end_date: str) -> str:
    """Retrieve recent news headlines/articles for a ticker over a date range.

    Args:
        ticker: Ticker symbol.
        start_date: Start date in yyyy-mm-dd format.
        end_date: End date in yyyy-mm-dd format.
    """
    return get_news.func(ticker, start_date, end_date)


@mcp.tool()
def get_macro_news(
    curr_date: str, look_back_days: int | None = None, limit: int | None = None
) -> str:
    """Retrieve global/macroeconomic news headlines.

    Args:
        curr_date: Current date in yyyy-mm-dd format.
        look_back_days: Days to look back (omit for the configured default).
        limit: Max articles to return (omit for the configured default).
    """
    return get_global_news.func(curr_date, look_back_days, limit)


@mcp.tool()
def get_company_insider_transactions(ticker: str) -> str:
    """Retrieve insider-transaction information for a company.

    Args:
        ticker: Ticker symbol of the company.
    """
    return get_insider_transactions.func(ticker)


@mcp.tool()
def get_stocktwits_messages(ticker: str, limit: int = 30) -> str:
    """Retrieve recent StockTwits messages for a ticker (retail sentiment).

    Returns retail-trader posts indexed by cashtag, each carrying a
    user-labeled Bullish / Bearish tag (or none) plus the message body — a
    fast-moving retail-sentiment signal. Degrades gracefully to a placeholder
    when the source is unavailable.

    Args:
        ticker: Ticker symbol (the cashtag, e.g. AAPL).
        limit: Max messages to return (default 30).
    """
    return fetch_stocktwits_messages(ticker, limit=limit)


@mcp.tool()
def get_reddit_posts(ticker: str) -> str:
    """Retrieve recent Reddit posts mentioning a ticker (community sentiment).

    Searches r/wallstreetbets, r/stocks, and r/investing over the past ~7 days
    and returns posts with engagement signal (upvotes, comment counts) and body
    excerpts. Degrades gracefully to a placeholder when no posts are found.

    Args:
        ticker: Ticker symbol.
    """
    return fetch_reddit_posts(ticker)


@mcp.tool()
def get_macro_indicator(
    indicator: str, curr_date: str, look_back_days: int | None = None
) -> str:
    """Retrieve a macroeconomic indicator time series from FRED.

    Covers policy rates, Treasury yields, inflation, labor, and growth. Returns
    the series title, units, frequency, latest value, change over the window,
    and a recent observation table. Requires FRED_API_KEY in the environment.

    Args:
        indicator: Friendly alias ('cpi', 'fed_funds_rate', '10y_treasury',
            'unemployment', 'vix', 'yield_curve', 'real_gdp', ...) or a raw
            FRED series ID such as 'CPIAUCSL'.
        curr_date: Current date in yyyy-mm-dd format (end of the window).
        look_back_days: Trailing window length (omit for a 1-year window).
    """
    return get_macro_indicators.func(indicator, curr_date, look_back_days)


@mcp.tool()
def get_event_prediction_markets(topic: str, limit: int | None = None) -> str:
    """Retrieve live market-implied probabilities for forward-looking events.

    Sources Polymarket for the most-traded open markets matching the topic,
    each with implied probability, volume, resolution date, and recent move.

    Args:
        topic: Event keyword(s), e.g. 'Fed rate cut', 'recession 2026'.
        limit: Max markets to return (omit for a default of 6).
    """
    return get_prediction_markets.func(topic, limit)


# --------------------------------------------------------------------------- #
# Fundamentals tools
# --------------------------------------------------------------------------- #
@mcp.tool()
def get_company_fundamentals(ticker: str, curr_date: str) -> str:
    """Retrieve comprehensive fundamental data for a ticker.

    Args:
        ticker: Ticker symbol of the company.
        curr_date: Current trading date in yyyy-mm-dd format.
    """
    return get_fundamentals.func(ticker, curr_date)


@mcp.tool()
def get_company_balance_sheet(
    ticker: str, freq: str = "quarterly", curr_date: str | None = None
) -> str:
    """Retrieve balance sheet data for a ticker.

    Args:
        ticker: Ticker symbol of the company.
        freq: Reporting frequency, 'annual' or 'quarterly' (default quarterly).
        curr_date: Current trading date in yyyy-mm-dd format.
    """
    return get_balance_sheet.func(ticker, freq, curr_date)


@mcp.tool()
def get_company_cashflow(
    ticker: str, freq: str = "quarterly", curr_date: str | None = None
) -> str:
    """Retrieve cash-flow-statement data for a ticker.

    Args:
        ticker: Ticker symbol of the company.
        freq: Reporting frequency, 'annual' or 'quarterly' (default quarterly).
        curr_date: Current trading date in yyyy-mm-dd format.
    """
    return get_cashflow.func(ticker, freq, curr_date)


@mcp.tool()
def get_company_income_statement(
    ticker: str, freq: str = "quarterly", curr_date: str | None = None
) -> str:
    """Retrieve income-statement data for a ticker.

    Args:
        ticker: Ticker symbol of the company.
        freq: Reporting frequency, 'annual' or 'quarterly' (default quarterly).
        curr_date: Current trading date in yyyy-mm-dd format.
    """
    return get_income_statement.func(ticker, freq, curr_date)


# --------------------------------------------------------------------------- #
# Identity / reflection helpers
# --------------------------------------------------------------------------- #
@mcp.tool()
def resolve_instrument(ticker: str, asset_type: str = "stock") -> str:
    """Resolve the real instrument identity and return an anchoring context.

    Call this first. It does a deterministic yfinance lookup (company name,
    sector/industry, exchange) and returns a context string that every agent
    should be anchored to, so the analysis never substitutes a different
    company than the one the ticker refers to.

    Args:
        ticker: Ticker symbol, preserving any exchange suffix.
        asset_type: 'stock' (default) or 'crypto'.
    """
    identity = resolve_instrument_identity(ticker)
    return build_instrument_context(ticker, asset_type, identity)


@mcp.tool()
def get_realized_return(
    ticker: str, trade_date: str, holding_days: int = 5
) -> dict:
    """Compute the realized raw and alpha return after a past decision.

    Used by the reflection step: given a prior decision's trade date, returns
    the raw return and the alpha versus the market-appropriate benchmark over
    the holding window. ``available`` is False when prices aren't out yet.

    Args:
        ticker: Ticker symbol.
        trade_date: The decision/trade date in yyyy-mm-dd format.
        holding_days: Holding window in trading days (default 5).
    """
    return fetch_realized_return(ticker, trade_date, holding_days)


def main() -> None:
    """Console-script entry point: run the server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
