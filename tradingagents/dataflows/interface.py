import logging
from typing import Annotated

logger = logging.getLogger(__name__)

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
from .alpha_vantage_common import AlphaVantageRateLimitError
from .jintel import (
    get_stock as get_jintel_stock,
    get_indicator as get_jintel_indicator,
    get_fundamentals as get_jintel_fundamentals,
    get_balance_sheet as get_jintel_balance_sheet,
    get_cashflow as get_jintel_cashflow,
    get_income_statement as get_jintel_income_statement,
    get_news as get_jintel_news,
    get_global_news as get_jintel_global_news,
    get_insider_transactions as get_jintel_insider_transactions,
    get_filings as get_jintel_filings,
    get_macro_series as get_jintel_macro_series,
    get_top_holders as get_jintel_top_holders,
    JintelRateLimitError,
    JintelNoDataError,
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
            "get_income_statement"
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
    "extended_data": {
        "description": "SEC filings, US macro, 13F holdings (Jintel-only)",
        "tools": [
            "get_filings",
            "get_macro_series",
            "get_top_holders",
        ]
    }
}

VENDOR_LIST = [
    "yfinance",
    "jintel",
    "alpha_vantage",
]

# Mapping of methods to their vendor-specific implementations.
# Dict order defines the implicit fallback order in route_to_vendor when the
# configured primary vendor fails: jintel sits ahead of alpha_vantage so the
# unified GraphQL backend is preferred over the per-call rate-limited REST
# fallback.
VENDOR_METHODS = {
    # core_stock_apis
    "get_stock_data": {
        "yfinance": get_YFin_data_online,
        "jintel": get_jintel_stock,
        "alpha_vantage": get_alpha_vantage_stock,
    },
    # technical_indicators
    "get_indicators": {
        "yfinance": get_stock_stats_indicators_window,
        "jintel": get_jintel_indicator,
        "alpha_vantage": get_alpha_vantage_indicator,
    },
    # fundamental_data
    "get_fundamentals": {
        "yfinance": get_yfinance_fundamentals,
        "jintel": get_jintel_fundamentals,
        "alpha_vantage": get_alpha_vantage_fundamentals,
    },
    "get_balance_sheet": {
        "yfinance": get_yfinance_balance_sheet,
        "jintel": get_jintel_balance_sheet,
        "alpha_vantage": get_alpha_vantage_balance_sheet,
    },
    "get_cashflow": {
        "yfinance": get_yfinance_cashflow,
        "jintel": get_jintel_cashflow,
        "alpha_vantage": get_alpha_vantage_cashflow,
    },
    "get_income_statement": {
        "yfinance": get_yfinance_income_statement,
        "jintel": get_jintel_income_statement,
        "alpha_vantage": get_alpha_vantage_income_statement,
    },
    # news_data
    "get_news": {
        "yfinance": get_news_yfinance,
        "jintel": get_jintel_news,
        "alpha_vantage": get_alpha_vantage_news,
    },
    "get_global_news": {
        "yfinance": get_global_news_yfinance,
        "jintel": get_jintel_global_news,
        "alpha_vantage": get_alpha_vantage_global_news,
    },
    "get_insider_transactions": {
        "yfinance": get_yfinance_insider_transactions,
        "jintel": get_jintel_insider_transactions,
        "alpha_vantage": get_alpha_vantage_insider_transactions,
    },
    # extended_data -- jintel-only (no yfinance / alpha_vantage equivalent).
    # When jintel raises JintelNoDataError the dispatcher exhausts the chain
    # and surfaces RuntimeError to the caller, which is the desired behavior.
    "get_filings": {
        "jintel": get_jintel_filings,
    },
    "get_macro_series": {
        "jintel": get_jintel_macro_series,
    },
    "get_top_holders": {
        "jintel": get_jintel_top_holders,
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
    """Route method calls to appropriate vendor implementation with fallback support."""
    category = get_category_for_method(method)
    vendor_config = get_vendor(category, method)
    primary_vendors = [v.strip() for v in vendor_config.split(',')]

    if method not in VENDOR_METHODS:
        raise ValueError(f"Method '{method}' not supported")

    # Build fallback chain: primary vendors first, then remaining available vendors
    all_available_vendors = list(VENDOR_METHODS[method].keys())
    fallback_vendors = primary_vendors.copy()
    for vendor in all_available_vendors:
        if vendor not in fallback_vendors:
            fallback_vendors.append(vendor)

    for vendor in fallback_vendors:
        if vendor not in VENDOR_METHODS[method]:
            continue

        vendor_impl = VENDOR_METHODS[method][vendor]
        impl_func = vendor_impl[0] if isinstance(vendor_impl, list) else vendor_impl

        try:
            return impl_func(*args, **kwargs)
        except AlphaVantageRateLimitError as e:
            logger.warning(
                "vendor fallback: %s rate-limited on %s -> trying next vendor (%s)",
                vendor, method, e,
            )
            continue
        except JintelRateLimitError as e:
            logger.warning(
                "vendor fallback: %s rate-limited on %s -> trying next vendor (%s)",
                vendor, method, e,
            )
            continue
        except JintelNoDataError as e:
            logger.warning(
                "vendor fallback: %s no-data on %s -> trying next vendor (%s)",
                vendor, method, e,
            )
            continue

    raise RuntimeError(f"No available vendor for '{method}'")