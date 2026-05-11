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
from .yfinance_etf import (
    get_etf_profile as get_yfinance_etf_profile,
    get_etf_holdings as get_yfinance_etf_holdings,
    get_top_holding_tickers as get_yfinance_top_holding_tickers,
)
from .alpha_vantage_etf import (
    get_etf_profile as get_alpha_vantage_etf_profile,
    get_etf_holdings as get_alpha_vantage_etf_holdings,
    get_top_holding_tickers as get_alpha_vantage_top_holding_tickers,
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
from .alpha_vantage_common import AlphaVantageRateLimitError
from .etf_utils import ETF_PROTECTED_METHODS, etf_placeholder

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
    "etf_data": {
        "description": "ETF-specific profile and holdings",
        "tools": [
            "get_etf_profile",
            "get_etf_holdings",
            # Structured top-holdings extractor used internally by the
            # drill-down tool. Same vendor pool as the other etf_data
            # methods; never exposed to the LLM directly.
            "get_top_holding_tickers",
        ]
    }
}

VENDOR_LIST = [
    "yfinance",
    "alpha_vantage",
]

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
        "alpha_vantage": get_alpha_vantage_insider_transactions,
        "yfinance": get_yfinance_insider_transactions,
    },
    # etf_data — yfinance covers US and HK ETFs; Alpha Vantage covers any
    # symbol Alpha Vantage tracks (mostly US). A-share ETF support arrives
    # with the AKShare vendor in a separate change.
    "get_etf_profile": {
        "yfinance": get_yfinance_etf_profile,
        "alpha_vantage": get_alpha_vantage_etf_profile,
    },
    "get_etf_holdings": {
        "yfinance": get_yfinance_etf_holdings,
        "alpha_vantage": get_alpha_vantage_etf_holdings,
    },
    # Structured top-holdings extractor — returns ``[(ticker, name, weight_pct)]``
    # for use by the drill-down orchestrator. Routed like the other ETF methods,
    # so fallback works the same way (yfinance ↔ alpha_vantage).
    "get_top_holding_tickers": {
        "yfinance": get_yfinance_top_holding_tickers,
        "alpha_vantage": get_alpha_vantage_top_holding_tickers,
    },
}


def _apply_etf_placeholders() -> None:
    """Wrap every registered vendor impl of a company-financial method with
    the ETF placeholder.

    Done at the dispatch layer (not on each vendor function) because the
    placeholder is a *tool-level* semantic — ETF tickers should be
    redirected to ETF tools — not a vendor concern. Centralizing here means
    new vendors get ETF protection automatically and the vendor modules
    stay vendor-pure. Direct calls into vendor modules (bypassing
    ``route_to_vendor``) intentionally do NOT trigger the placeholder —
    they remain thin wrappers over the upstream API.
    """
    for method, label in ETF_PROTECTED_METHODS.items():
        for vendor in list(VENDOR_METHODS[method]):
            VENDOR_METHODS[method][vendor] = etf_placeholder(label)(
                VENDOR_METHODS[method][vendor]
            )


_apply_etf_placeholders()

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