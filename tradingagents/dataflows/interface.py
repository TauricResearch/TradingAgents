from typing import Annotated

# Import from vendor-specific modules
from .local import get_YFin_data, get_finnhub_news, get_finnhub_company_insider_sentiment, get_finnhub_company_insider_transactions, get_simfin_balance_sheet, get_simfin_cashflow, get_simfin_income_statements, get_reddit_global_news, get_reddit_company_news
from .y_finance import get_YFin_data_online, get_stock_stats_indicators_window, get_balance_sheet as get_yfinance_balance_sheet, get_cashflow as get_yfinance_cashflow, get_income_statement as get_yfinance_income_statement, get_insider_transactions as get_yfinance_insider_transactions
from .google import get_google_news
from .openai import get_stock_news_openai, get_global_news_openai, get_fundamentals_openai
from .alpha_vantage import (
    get_stock as get_alpha_vantage_stock,
    get_indicator as get_alpha_vantage_indicator,
    get_fundamentals as get_alpha_vantage_fundamentals,
    get_balance_sheet as get_alpha_vantage_balance_sheet,
    get_cashflow as get_alpha_vantage_cashflow,
    get_income_statement as get_alpha_vantage_income_statement,
    get_insider_transactions as get_alpha_vantage_insider_transactions,
    get_news as get_alpha_vantage_news
)
from .alpha_vantage_common import AlphaVantageRateLimitError

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
        "description": "News (public/insiders, original/processed)",
        "tools": [
            "get_news",
            "get_global_news",
            "get_insider_sentiment",
            "get_insider_transactions",
        ]
    }
}

VENDOR_LIST = [
    "local",
    "yfinance",
    "openai",
    "google"
]

# Mapping of methods to their vendor-specific implementations
VENDOR_METHODS = {
    # core_stock_apis
    "get_stock_data": {
        "alpha_vantage": get_alpha_vantage_stock,
        "yfinance": get_YFin_data_online,
        "local": get_YFin_data,
    },
    # technical_indicators
    "get_indicators": {
        "alpha_vantage": get_alpha_vantage_indicator,
        "yfinance": get_stock_stats_indicators_window,
        "local": get_stock_stats_indicators_window
    },
    # fundamental_data
    "get_fundamentals": {
        "alpha_vantage": get_alpha_vantage_fundamentals,
        "openai": get_fundamentals_openai,
    },
    "get_balance_sheet": {
        "alpha_vantage": get_alpha_vantage_balance_sheet,
        "yfinance": get_yfinance_balance_sheet,
        "local": get_simfin_balance_sheet,
    },
    "get_cashflow": {
        "alpha_vantage": get_alpha_vantage_cashflow,
        "yfinance": get_yfinance_cashflow,
        "local": get_simfin_cashflow,
    },
    "get_income_statement": {
        "alpha_vantage": get_alpha_vantage_income_statement,
        "yfinance": get_yfinance_income_statement,
        "local": get_simfin_income_statements,
    },
    # news_data
    "get_news": {
        "alpha_vantage": get_alpha_vantage_news,
        "openai": get_stock_news_openai,
        "google": get_google_news,
        "local": [get_finnhub_news, get_reddit_company_news, get_google_news],
    },
    "get_global_news": {
        "openai": get_global_news_openai,
        "local": get_reddit_global_news
    },
    "get_insider_sentiment": {
        "local": get_finnhub_company_insider_sentiment
    },
    "get_insider_transactions": {
        "alpha_vantage": get_alpha_vantage_insider_transactions,
        "yfinance": get_yfinance_insider_transactions,
        "local": get_finnhub_company_insider_transactions,
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

# Route method calls to vendors
def route_to_vendor(method: str, *args, **kwargs):
    """Route method calls to appropriate vendor implementation with proper primary/fallback behavior."""

    category = get_category_for_method(method)
    vendor_config = get_vendor(category, method)

    if method not in VENDOR_METHODS:
        raise ValueError(f"Method '{method}' not supported")

    # Parse configured vendors
    primary_vendors = [v.strip() for v in vendor_config.split(",")]
    all_available_vendors = list(VENDOR_METHODS[method].keys())

    # Compute fallback vendors (ones NOT listed as primary)
    fallback_vendors = [v for v in all_available_vendors if v not in primary_vendors]

    print(f"DEBUG: {method} - Primary vendors: {primary_vendors} | Fallback vendors: {fallback_vendors}")

    results = []
    successful_vendor = None

    # Attempt all primary vendors
    for vendor in primary_vendors:
        if vendor not in VENDOR_METHODS[method]:
            print(f"INFO: Primary vendor '{vendor}' not supported for method '{method}'")
            continue

        vendor_impl = VENDOR_METHODS[method][vendor]
        vendor_methods = vendor_impl if isinstance(vendor_impl, list) else [vendor_impl]

        print(f"DEBUG: Trying PRIMARY vendor '{vendor}' ({len(vendor_methods)} implementations)")

        vendor_results = []
        for impl_func in vendor_methods:
            try:
                print(f"DEBUG: Calling {impl_func.__name__} from vendor '{vendor}'...")
                result = impl_func(*args, **kwargs)
                vendor_results.append(result)
                print(f"SUCCESS: {impl_func.__name__} succeeded for vendor '{vendor}'")

            except AlphaVantageRateLimitError as e:
                print(f"RATE_LIMIT: Vendor '{vendor}' exceeded rate limit, trying next primary vendor")
                print(f"DEBUG: {e}")
                break

            except Exception as e:
                print(f"FAILED: {impl_func.__name__} for vendor '{vendor}' - {e}")
                continue

        if vendor_results:
            results.extend(vendor_results)
            successful_vendor = vendor
        else:
            print(f"FAILED: Primary vendor '{vendor}' returned no results")

    # If ANY primary vendor succeeded then STOP EARLY
    if successful_vendor:
        print(f"FINAL: Completed with primary vendor(s). Total results: {len(results)}")
        return results[0] if len(results) == 1 else '\n'.join(str(r) for r in results)

    print("WARNING: All primary vendors failed. Attempting fallback vendors...")

    # Fallback logic
    for vendor in fallback_vendors:
        vendor_impl = VENDOR_METHODS[method][vendor]
        vendor_methods = vendor_impl if isinstance(vendor_impl, list) else [vendor_impl]

        print(f"DEBUG: Trying FALLBACK vendor '{vendor}'")

        for impl_func in vendor_methods:
            try:
                result = impl_func(*args, **kwargs)
                print(f"SUCCESS: Fallback vendor '{vendor}' succeeded via {impl_func.__name__}")
                return result

            except Exception as e:
                print(f"FAILED: Fallback vendor '{vendor}' - {e}")
                continue

    # If all vendors fail
    raise RuntimeError(f"All vendors failed for method '{method}'")
