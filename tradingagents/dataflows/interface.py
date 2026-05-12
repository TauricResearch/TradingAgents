import logging
import re
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
from .tushare_data import (
    get_tushare_stock,
    get_tushare_indicators,
    get_tushare_fundamentals,
    get_tushare_balance_sheet,
    get_tushare_cashflow,
    get_tushare_income_statement,
    get_tushare_insider_transactions,
    get_tushare_news,
    get_tushare_global_news,
)
from .akshare_data import (
    get_akshare_stock,
    get_akshare_indicators,
    get_akshare_fundamentals,
    get_akshare_balance_sheet,
    get_akshare_cashflow,
    get_akshare_income_statement,
    get_akshare_insider_transactions,
    get_akshare_news,
    get_akshare_global_news,
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
    }
}

VENDOR_LIST = [
    "yfinance",
    "alpha_vantage",
    "tushare",
    "akshare",
]

# Mapping of methods to their vendor-specific implementations
VENDOR_METHODS = {
    # core_stock_apis
    "get_stock_data": {
        "alpha_vantage": get_alpha_vantage_stock,
        "yfinance": get_YFin_data_online,
        "tushare": get_tushare_stock,
        "akshare": get_akshare_stock,
    },
    # technical_indicators
    "get_indicators": {
        "alpha_vantage": get_alpha_vantage_indicator,
        "yfinance": get_stock_stats_indicators_window,
        "tushare": get_tushare_indicators,
        "akshare": get_akshare_indicators,
    },
    # fundamental_data
    "get_fundamentals": {
        "alpha_vantage": get_alpha_vantage_fundamentals,
        "yfinance": get_yfinance_fundamentals,
        "tushare": get_tushare_fundamentals,
        "akshare": get_akshare_fundamentals,
    },
    "get_balance_sheet": {
        "alpha_vantage": get_alpha_vantage_balance_sheet,
        "yfinance": get_yfinance_balance_sheet,
        "tushare": get_tushare_balance_sheet,
        "akshare": get_akshare_balance_sheet,
    },
    "get_cashflow": {
        "alpha_vantage": get_alpha_vantage_cashflow,
        "yfinance": get_yfinance_cashflow,
        "tushare": get_tushare_cashflow,
        "akshare": get_akshare_cashflow,
    },
    "get_income_statement": {
        "alpha_vantage": get_alpha_vantage_income_statement,
        "yfinance": get_yfinance_income_statement,
        "tushare": get_tushare_income_statement,
        "akshare": get_akshare_income_statement,
    },
    # news_data
    "get_news": {
        "alpha_vantage": get_alpha_vantage_news,
        "yfinance": get_news_yfinance,
        "tushare": get_tushare_news,
        "akshare": get_akshare_news,
    },
    "get_global_news": {
        "yfinance": get_global_news_yfinance,
        "alpha_vantage": get_alpha_vantage_global_news,
        "tushare": get_tushare_global_news,
        "akshare": get_akshare_global_news,
    },
    "get_insider_transactions": {
        "alpha_vantage": get_alpha_vantage_insider_transactions,
        "yfinance": get_yfinance_insider_transactions,
        "tushare": get_tushare_insider_transactions,
        "akshare": get_akshare_insider_transactions,
    },
}

def detect_vendor_for_ticker(symbol: str) -> str | None:
    """
    Detect the appropriate vendor based on ticker symbol format.
    Returns "akshare" for A-share/HK tickers, None for others (use config default).
    """
    if not symbol or not isinstance(symbol, str):
        return None

    s = symbol.strip().upper()

    # A股格式: 600000.SH, 600000.SS, 000001.SZ
    if re.match(r'^\d{6}\.(SH|SS|SZ)$', s):
        return "akshare"

    # A股格式: SH600000, SS600000, SZ000001
    if re.match(r'^(SH|SS|SZ)\d{6}$', s):
        return "akshare"

    # 纯6位数字（A股）
    if re.match(r'^\d{6}$', s):
        return "akshare"

    # 港股格式: 0700.HK, 00700.HK
    if re.match(r'^\d{4,5}\.HK$', s):
        return "akshare"

    # 港股格式: HK0700, HK00700
    if re.match(r'^HK\d{4,5}$', s):
        return "akshare"

    return None


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

    if method not in VENDOR_METHODS:
        raise ValueError(f"Method '{method}' not supported")

    # Auto-detect vendor based on ticker format
    auto_vendor = None
    if method != "get_global_news" and args:
        # First arg is typically the ticker/symbol
        auto_vendor = detect_vendor_for_ticker(str(args[0]))

    # Get config-based vendor preferences
    vendor_config = get_vendor(category, method)
    config_vendors = [v.strip() for v in vendor_config.split(',')]

    # Build fallback chain
    if auto_vendor and auto_vendor in VENDOR_METHODS.get(method, {}):
        # Auto-detected vendor goes first, then config-based, then remaining
        primary_vendors = [auto_vendor]
        for v in config_vendors:
            if v not in primary_vendors:
                primary_vendors.append(v)
    else:
        primary_vendors = config_vendors

    # Append remaining available vendors not yet in the chain
    all_available_vendors = list(VENDOR_METHODS[method].keys())
    fallback_vendors = primary_vendors.copy()
    for vendor in all_available_vendors:
        if vendor not in fallback_vendors:
            fallback_vendors.append(vendor)

    errors_collected = {}

    for vendor in fallback_vendors:
        if vendor not in VENDOR_METHODS[method]:
            continue

        if vendor == "yfinance" and auto_vendor == "akshare":
            logger.warning(
                "Attempting yfinance for A-share ticker '%s' as fallback — "
                "this will likely fail. Please check your akshare/tushare "
                "configuration.",
                args[0] if args else "?"
            )

        vendor_impl = VENDOR_METHODS[method][vendor]
        impl_func = vendor_impl[0] if isinstance(vendor_impl, list) else vendor_impl

        try:
            return impl_func(*args, **kwargs)
        except AlphaVantageRateLimitError:
            errors_collected[vendor] = "rate limit exceeded"
            continue  # Only rate limits trigger fallback
        except Exception as e:
            errors_collected[vendor] = str(e)
            if vendor == auto_vendor:
                logger.warning(
                    "Auto-detected vendor '%s' failed for %s(%s): %s. "
                    "Falling through to next vendor.",
                    vendor, method, args[0] if args else "?", e
                )
                continue
            raise

    raise RuntimeError(
        f"All vendors failed for '{method}' "
        f"(ticker={args[0] if args else '?'}). "
        f"Tried: {errors_collected}"
    )