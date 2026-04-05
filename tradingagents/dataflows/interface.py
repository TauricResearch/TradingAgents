from typing import Annotated

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
from .binance import get_binance_klines, get_binance_indicators_window

from .config import get_config

TOOLS_CATEGORIES = {
    "core_stock_apis": {
        "description": "OHLCV price data",
        "tools": ["get_stock_data"],
    },
    "technical_indicators": {
        "description": "Technical analysis indicators",
        "tools": ["get_indicators"],
    },
    "fundamental_data": {
        "description": "Company fundamentals",
        "tools": [
            "get_fundamentals",
            "get_balance_sheet",
            "get_cashflow",
            "get_income_statement",
        ],
    },
    "news_data": {
        "description": "News and insider data",
        "tools": [
            "get_news",
            "get_global_news",
            "get_insider_transactions",
        ],
    },
}

VENDOR_LIST = ["binance", "alpha_vantage"]

VENDOR_METHODS = {
    # core_stock_apis
    "get_stock_data": {
        "binance": get_binance_klines,
        "alpha_vantage": get_alpha_vantage_stock,
    },
    # technical_indicators
    "get_indicators": {
        "binance": get_binance_indicators_window,
        "alpha_vantage": get_alpha_vantage_indicator,
    },
    # fundamental_data — Binance is a crypto exchange and does not provide these
    "get_fundamentals": {
        "alpha_vantage": get_alpha_vantage_fundamentals,
    },
    "get_balance_sheet": {
        "alpha_vantage": get_alpha_vantage_balance_sheet,
    },
    "get_cashflow": {
        "alpha_vantage": get_alpha_vantage_cashflow,
    },
    "get_income_statement": {
        "alpha_vantage": get_alpha_vantage_income_statement,
    },
    # news_data — Binance does not provide news feeds
    "get_news": {
        "alpha_vantage": get_alpha_vantage_news,
    },
    "get_global_news": {
        "alpha_vantage": get_alpha_vantage_global_news,
    },
    "get_insider_transactions": {
        "alpha_vantage": get_alpha_vantage_insider_transactions,
    },
}


def get_category_for_method(method: str) -> str:
    """Get the category that contains the specified method."""
    for category, info in TOOLS_CATEGORIES.items():
        if method in info["tools"]:
            return category
    raise ValueError(f"Method '{method}' not found in any category")


def get_vendor(category: str, method: str | None = None) -> str:
    """Get the configured vendor for a data category or specific tool.

    Tool-level configuration takes precedence over category-level.
    """
    config = get_config()

    if method:
        tool_vendors = config.get("tool_vendors", {})
        if method in tool_vendors:
            return tool_vendors[method]

    return config.get("data_vendors", {}).get(category, "binance")


def route_to_vendor(method: str, *args, **kwargs):
    """Route a method call to the appropriate vendor implementation with fallback."""
    category = get_category_for_method(method)
    vendor_config = get_vendor(category, method)
    primary_vendors = [v.strip() for v in vendor_config.split(",")]

    if method not in VENDOR_METHODS:
        raise ValueError(f"Method '{method}' not supported")

    all_available = list(VENDOR_METHODS[method].keys())
    fallback_chain = primary_vendors.copy()
    for vendor in all_available:
        if vendor not in fallback_chain:
            fallback_chain.append(vendor)

    for vendor in fallback_chain:
        if vendor not in VENDOR_METHODS[method]:
            continue

        impl_func = VENDOR_METHODS[method][vendor]
        if isinstance(impl_func, list):
            impl_func = impl_func[0]

        try:
            return impl_func(*args, **kwargs)
        except AlphaVantageRateLimitError:
            continue  # only rate limits trigger fallback

    raise RuntimeError(f"No available vendor for '{method}'")
