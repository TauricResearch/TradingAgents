import logging

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
from .yfinance_client import (
    get_stock_data as get_yfinance_stock,
    get_indicators as get_yfinance_indicators,
    get_fundamentals as get_yfinance_fundamentals,
    get_balance_sheet as get_yfinance_balance_sheet,
    get_cashflow as get_yfinance_cashflow,
    get_income_statement as get_yfinance_income_statement,
    get_news as get_yfinance_news,
    get_insider_transactions as get_yfinance_insider_transactions,
)

from .config import get_config

logger = logging.getLogger(__name__)

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

VENDOR_LIST = ["binance", "yfinance", "alpha_vantage"]

VENDOR_METHODS = {
    # core_stock_apis — binance (crypto), yfinance (universal), alpha_vantage (stocks)
    "get_stock_data": {
        "binance": get_binance_klines,
        "yfinance": get_yfinance_stock,
        "alpha_vantage": get_alpha_vantage_stock,
    },
    # technical_indicators
    "get_indicators": {
        "binance": get_binance_indicators_window,
        "yfinance": get_yfinance_indicators,
        "alpha_vantage": get_alpha_vantage_indicator,
    },
    # fundamental_data — yfinance primary (free, no API key), alpha_vantage fallback
    # Binance is a crypto exchange and does not provide these endpoints
    "get_fundamentals": {
        "yfinance": get_yfinance_fundamentals,
        "alpha_vantage": get_alpha_vantage_fundamentals,
    },
    "get_balance_sheet": {
        "yfinance": get_yfinance_balance_sheet,
        "alpha_vantage": get_alpha_vantage_balance_sheet,
    },
    "get_cashflow": {
        "yfinance": get_yfinance_cashflow,
        "alpha_vantage": get_alpha_vantage_cashflow,
    },
    "get_income_statement": {
        "yfinance": get_yfinance_income_statement,
        "alpha_vantage": get_alpha_vantage_income_statement,
    },
    # news_data
    "get_news": {
        "yfinance": get_yfinance_news,
        "alpha_vantage": get_alpha_vantage_news,
    },
    "get_global_news": {
        "alpha_vantage": get_alpha_vantage_global_news,
    },
    "get_insider_transactions": {
        "yfinance": get_yfinance_insider_transactions,
        "alpha_vantage": get_alpha_vantage_insider_transactions,
    },
}

# Sensible fallback vendor per category when config key is missing
_CATEGORY_DEFAULTS = {
    "core_stock_apis": "yfinance,alpha_vantage",
    "technical_indicators": "yfinance,alpha_vantage",
    "fundamental_data": "yfinance,alpha_vantage",
    "news_data": "yfinance,alpha_vantage",
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
    Falls back to sensible per-category defaults instead of a single global default.
    """
    config = get_config()

    if method:
        tool_vendors = config.get("tool_vendors", {})
        if method in tool_vendors:
            return tool_vendors[method]

    return config.get("data_vendors", {}).get(
        category, _CATEGORY_DEFAULTS.get(category, "yfinance,alpha_vantage")
    )


def route_to_vendor(method: str, *args, **kwargs):
    """Route a method call to the appropriate vendor with fallback.

    Fallback triggers on:
    - Rate limit errors
    - Any other exception (network, invalid symbol, etc.)
    - Empty or whitespace-only response
    """
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

    last_error: Exception | None = None
    for vendor in fallback_chain:
        if vendor not in VENDOR_METHODS[method]:
            continue

        impl_func = VENDOR_METHODS[method][vendor]
        if isinstance(impl_func, list):
            impl_func = impl_func[0]

        try:
            result = impl_func(*args, **kwargs)
            if result and str(result).strip():
                return result
            logger.warning(
                "Vendor '%s' returned empty for '%s', trying next", vendor, method
            )
        except AlphaVantageRateLimitError:
            logger.warning("Vendor '%s' rate-limited for '%s', trying next", vendor, method)
        except Exception as e:
            last_error = e
            logger.warning(
                "Vendor '%s' failed for '%s': %s, trying next", vendor, method, e
            )

    if last_error:
        raise RuntimeError(
            f"All vendors exhausted for '{method}'. Last error: {last_error}"
        )
    raise RuntimeError(f"All vendors returned empty for '{method}'")
