"""Finnhub vendor facade module.

Re-exports all public functions from the Finnhub sub-modules so callers can
import everything from a single entry point, mirroring the ``alpha_vantage.py``
facade pattern.

Usage:
    from tradingagents.dataflows.finnhub import (
        get_stock_candles,
        get_quote,
        get_company_profile,
        ...
    )
"""

# Stock price data
from .finnhub_stock import get_stock_candles, get_quote

# Fundamental data
from .finnhub_fundamentals import (
    get_company_profile,
    get_financial_statements,
    get_basic_financials,
)

# News and insider transactions
from .finnhub_news import (
    get_company_news,
    get_market_news,
    get_insider_transactions,
)

# Market-wide scanner data
from .finnhub_scanner import (
    get_market_movers_finnhub,
    get_market_indices_finnhub,
    get_sector_performance_finnhub,
    get_topic_news_finnhub,
    get_earnings_calendar_finnhub,
    get_economic_calendar_finnhub,
)

# Technical indicators
from .finnhub_indicators import get_indicator_finnhub

# Exception hierarchy (re-exported for callers that need to catch Finnhub errors)
from .finnhub_common import (
    FinnhubError,
    APIKeyInvalidError,
    RateLimitError,
    ThirdPartyError,
    ThirdPartyTimeoutError,
    ThirdPartyParseError,
)

__all__ = [
    # Stock
    "get_stock_candles",
    "get_quote",
    # Fundamentals
    "get_company_profile",
    "get_financial_statements",
    "get_basic_financials",
    # News
    "get_company_news",
    "get_market_news",
    "get_insider_transactions",
    # Scanner
    "get_market_movers_finnhub",
    "get_market_indices_finnhub",
    "get_sector_performance_finnhub",
    "get_topic_news_finnhub",
    "get_earnings_calendar_finnhub",
    "get_economic_calendar_finnhub",
    # Indicators
    "get_indicator_finnhub",
    # Exceptions
    "FinnhubError",
    "APIKeyInvalidError",
    "RateLimitError",
    "ThirdPartyError",
    "ThirdPartyTimeoutError",
    "ThirdPartyParseError",
]
