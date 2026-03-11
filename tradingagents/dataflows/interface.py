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

# Import Korean market data sources
from .korea_finance import (
    get_krx_stock_data as get_krx_stock_data_impl,
    get_krx_indicators as get_krx_indicators_impl,
    get_exchange_rate as get_exchange_rate_impl,
    get_korea_index_data as get_korea_index_impl,
    get_investor_trading_data as get_investor_trading_impl,
    get_krx_fundamentals as get_krx_fundamentals_impl,
)
from .korea_news import (
    get_korean_news as get_korean_news_impl,
    get_korean_global_news as get_korean_global_news_impl,
)
from .dart_api import (
    get_dart_financial_statements as get_dart_financials_impl,
    get_dart_disclosures as get_dart_disclosures_impl,
    get_dart_major_shareholders as get_dart_shareholders_impl,
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
    # ── Korean Market Categories ─────────────────────────────────────────
    "krx_stock_apis": {
        "description": "KRX (Korea Exchange) stock price data",
        "tools": [
            "get_krx_stock_data",
            "get_krx_indicators",
        ]
    },
    "korean_market_data": {
        "description": "Korean market context data (exchange rates, indices, investor flows)",
        "tools": [
            "get_exchange_rate",
            "get_korea_index",
            "get_investor_trading",
        ]
    },
    "korean_fundamental_data": {
        "description": "Korean company fundamentals (KRX + DART)",
        "tools": [
            "get_krx_fundamentals",
            "get_dart_financials",
            "get_dart_disclosures",
            "get_dart_shareholders",
        ]
    },
    "korean_news_data": {
        "description": "Korean financial news",
        "tools": [
            "get_korean_news",
            "get_korean_global_news",
        ]
    },
}

VENDOR_LIST = [
    "yfinance",
    "alpha_vantage",
    "krx",
    "dart",
    "naver",
]

# Mapping of methods to their vendor-specific implementations
VENDOR_METHODS = {
    # ── Existing: core_stock_apis ─────────────────────────────────────────
    "get_stock_data": {
        "alpha_vantage": get_alpha_vantage_stock,
        "yfinance": get_YFin_data_online,
    },
    # ── Existing: technical_indicators ────────────────────────────────────
    "get_indicators": {
        "alpha_vantage": get_alpha_vantage_indicator,
        "yfinance": get_stock_stats_indicators_window,
    },
    # ── Existing: fundamental_data ───────────────────────────────────────
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
    # ── Existing: news_data ──────────────────────────────────────────────
    "get_news": {
        "alpha_vantage": get_alpha_vantage_news,
        "yfinance": get_news_yfinance,
    },
    "get_global_news": {
        "yfinance": get_global_news_yfinance,
        "alpha_vantage": get_alpha_vantage_global_news,
    },
    "get_insider_transactions": {
        "alpha_vantage": get_alpha_vantage_insider_transactions,
        "yfinance": get_yfinance_insider_transactions,
    },
    # ── Korean: krx_stock_apis ───────────────────────────────────────────
    "get_krx_stock_data": {
        "krx": get_krx_stock_data_impl,
    },
    "get_krx_indicators": {
        "krx": get_krx_indicators_impl,
    },
    # ── Korean: korean_market_data ───────────────────────────────────────
    "get_exchange_rate": {
        "krx": get_exchange_rate_impl,
    },
    "get_korea_index": {
        "krx": get_korea_index_impl,
    },
    "get_investor_trading": {
        "krx": get_investor_trading_impl,
    },
    # ── Korean: korean_fundamental_data ──────────────────────────────────
    "get_krx_fundamentals": {
        "krx": get_krx_fundamentals_impl,
    },
    "get_dart_financials": {
        "dart": get_dart_financials_impl,
    },
    "get_dart_disclosures": {
        "dart": get_dart_disclosures_impl,
    },
    "get_dart_shareholders": {
        "dart": get_dart_shareholders_impl,
    },
    # ── Korean: korean_news_data ─────────────────────────────────────────
    "get_korean_news": {
        "naver": get_korean_news_impl,
    },
    "get_korean_global_news": {
        "naver": get_korean_global_news_impl,
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
        except AlphaVantageRateLimitError:
            continue  # Only rate limits trigger fallback

    raise RuntimeError(f"No available vendor for '{method}'")
