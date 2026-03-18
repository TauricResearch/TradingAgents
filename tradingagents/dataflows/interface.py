from typing import Annotated

# Import from vendor-specific modules
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
from .yfinance_scanner import (
    get_market_movers_yfinance,
    get_market_indices_yfinance,
    get_sector_performance_yfinance,
    get_industry_performance_yfinance,
    get_topic_news_yfinance,
)
from .alpha_vantage import (
    get_stock as get_alpha_vantage_stock,
    get_indicator as get_alpha_vantage_indicator,
    get_fundamentals as get_alpha_vantage_fundamentals,
    get_balance_sheet as get_alpha_vantage_balance_sheet,
    get_cashflow as get_alpha_vantage_cashflow,
    get_income_statement as get_alpha_vantage_income_statement,
    get_insider_transactions as get_alpha_vantage_insider_transactions,
    get_news as get_alpha_vantage_news,
    get_global_news as get_alpha_vantage_global_news,
)
from .alpha_vantage_scanner import (
    get_market_movers_alpha_vantage,
    get_market_indices_alpha_vantage,
    get_sector_performance_alpha_vantage,
    get_industry_performance_alpha_vantage,
    get_topic_news_alpha_vantage,
)
from .alpha_vantage_common import AlphaVantageError, AlphaVantageRateLimitError, RateLimitError
from .finnhub_common import FinnhubError
from .finnhub_news import get_insider_transactions as get_finnhub_insider_transactions
from .finnhub_scanner import (
    get_market_indices_finnhub,
    get_sector_performance_finnhub,
    get_topic_news_finnhub,
    get_earnings_calendar_finnhub,
    get_economic_calendar_finnhub,
)

# Configuration and routing logic
from .config import get_config

# Tools organized by category
TOOLS_CATEGORIES = {
    "core_stock_apis": {
        "description": "OHLCV stock price data",
        "tools": [
            "get_stock_data"
        ]
    },
    "technical_indicators": {
        "description": "Technical analysis indicators",
        "tools": [
            "get_indicators"
        ]
    },
    "fundamental_data": {
        "description": "Company fundamentals",
        "tools": [
            "get_fundamentals",
            "get_balance_sheet",
            "get_cashflow",
            "get_income_statement",
            "get_ttm_analysis",
        ]
    },
    "news_data": {
        "description": "News and insider data",
        "tools": [
            "get_news",
            "get_global_news",
            "get_insider_transactions",
        ]
    },
    "scanner_data": {
        "description": "Market-wide scanner data (movers, indices, sectors, industries)",
        "tools": [
            "get_market_movers",
            "get_market_indices",
            "get_sector_performance",
            "get_industry_performance",
            "get_topic_news",
        ]
    },
    "calendar_data": {
        "description": "Earnings and economic event calendars",
        "tools": [
            "get_earnings_calendar",
            "get_economic_calendar",
        ]
    },
}

VENDOR_LIST = [
    "yfinance",
    "alpha_vantage",
    "finnhub",
]

# Methods where cross-vendor fallback is safe (data contracts are fungible).
# All other methods fail-fast on primary vendor failure — see ADR 011.
FALLBACK_ALLOWED = {
    "get_stock_data",           # OHLCV is fungible across vendors
    "get_market_indices",       # SPY/DIA/QQQ quotes are fungible
    "get_sector_performance",   # ETF-based proxy, same approach
    "get_market_movers",        # Approximation acceptable for screening
    "get_industry_performance", # ETF-based proxy
}

# Mapping of methods to their vendor-specific implementations
VENDOR_METHODS = {
    # core_stock_apis
    "get_stock_data": {
        "alpha_vantage": get_alpha_vantage_stock,
        "yfinance": get_YFin_data_online,
    },
    # technical_indicators
    "get_indicators": {
        "alpha_vantage": get_alpha_vantage_indicator,
        "yfinance": get_stock_stats_indicators_window,
    },
    # fundamental_data
    "get_fundamentals": {
        "alpha_vantage": get_alpha_vantage_fundamentals,
        "yfinance": get_yfinance_fundamentals,
    },
    "get_balance_sheet": {
        "alpha_vantage": get_alpha_vantage_balance_sheet,
        "yfinance": get_yfinance_balance_sheet,
    },
    "get_cashflow": {
        "alpha_vantage": get_alpha_vantage_cashflow,
        "yfinance": get_yfinance_cashflow,
    },
    "get_income_statement": {
        "alpha_vantage": get_alpha_vantage_income_statement,
        "yfinance": get_yfinance_income_statement,
    },
    # news_data
    "get_news": {
        "alpha_vantage": get_alpha_vantage_news,
        "yfinance": get_news_yfinance,
    },
    "get_global_news": {
        "yfinance": get_global_news_yfinance,
        "alpha_vantage": get_alpha_vantage_global_news,
    },
    "get_insider_transactions": {
        "finnhub": get_finnhub_insider_transactions,
        "alpha_vantage": get_alpha_vantage_insider_transactions,
        "yfinance": get_yfinance_insider_transactions,
    },
    # scanner_data
    "get_market_movers": {
        "yfinance": get_market_movers_yfinance,
        "alpha_vantage": get_market_movers_alpha_vantage,
    },
    "get_market_indices": {
        "finnhub": get_market_indices_finnhub,
        "alpha_vantage": get_market_indices_alpha_vantage,
        "yfinance": get_market_indices_yfinance,
    },
    "get_sector_performance": {
        "finnhub": get_sector_performance_finnhub,
        "alpha_vantage": get_sector_performance_alpha_vantage,
        "yfinance": get_sector_performance_yfinance,
    },
    "get_industry_performance": {
        "alpha_vantage": get_industry_performance_alpha_vantage,
        "yfinance": get_industry_performance_yfinance,
    },
    "get_topic_news": {
        "finnhub": get_topic_news_finnhub,
        "alpha_vantage": get_topic_news_alpha_vantage,
        "yfinance": get_topic_news_yfinance,
    },
    # calendar_data — Finnhub only (unique capabilities)
    "get_earnings_calendar": {
        "finnhub": get_earnings_calendar_finnhub,
    },
    "get_economic_calendar": {
        "finnhub": get_economic_calendar_finnhub,
    },
}

def get_category_for_method(method: str) -> str:
    """Get the category that contains the specified method."""
    for category, info in TOOLS_CATEGORIES.items():
        if method in info["tools"]:
            return category
    raise ValueError(f"Method '{method}' not found in any category")

def get_vendor(category: str, method: str = None) -> str:
    """Get the configured vendor for a data category or specific tool method.
    Tool-level configuration takes precedence over category-level.
    """
    config = get_config()

    # Check tool-level configuration first (if method provided)
    if method:
        tool_vendors = config.get("tool_vendors", {})
        if method in tool_vendors:
            return tool_vendors[method]

    # Fall back to category-level configuration
    return config.get("data_vendors", {}).get(category, "default")

def route_to_vendor(method: str, *args, **kwargs):
    """Route method calls to appropriate vendor implementation with fallback support.

    Only methods in FALLBACK_ALLOWED get cross-vendor fallback.
    All others fail-fast on primary vendor failure (see ADR 011).
    """
    category = get_category_for_method(method)
    vendor_config = get_vendor(category, method)
    primary_vendors = [v.strip() for v in vendor_config.split(',')]

    if method not in VENDOR_METHODS:
        raise ValueError(f"Method '{method}' not supported")

    if method in FALLBACK_ALLOWED:
        # Build fallback chain: primary vendors first, then remaining available vendors
        all_available_vendors = list(VENDOR_METHODS[method].keys())
        vendors_to_try = primary_vendors.copy()
        for vendor in all_available_vendors:
            if vendor not in vendors_to_try:
                vendors_to_try.append(vendor)
    else:
        # Fail-fast: only try configured primary vendor(s)
        vendors_to_try = primary_vendors

    last_error = None
    tried = []
    for vendor in vendors_to_try:
        if vendor not in VENDOR_METHODS[method]:
            continue
        tried.append(vendor)

        vendor_impl = VENDOR_METHODS[method][vendor]
        impl_func = vendor_impl[0] if isinstance(vendor_impl, list) else vendor_impl

        try:
            return impl_func(*args, **kwargs)
        except (AlphaVantageError, FinnhubError, ConnectionError, TimeoutError) as exc:
            last_error = exc
            continue

    error_msg = f"All vendors failed for '{method}' (tried: {', '.join(tried)})"
    raise RuntimeError(error_msg) from last_error