from typing import Annotated
from functools import lru_cache
import hashlib
import json
import os
import time as _time

from tradingagents.log_utils import add_log, raw_data_store

# Debug mode - set to False to reduce logging verbosity
DEBUG_MODE = os.environ.get("TRADING_AGENTS_DEBUG", "false").lower() == "true"

def _debug_print(*args, **kwargs):
    """Print only when debug mode is enabled."""
    if DEBUG_MODE:
        print(*args, **kwargs)

# Simple in-memory cache for data requests within same analysis session
_request_cache = {}


def _make_cache_key(method: str, args: tuple, kwargs: dict) -> str:
    """Generate a cache key from method name and arguments."""
    # Convert args to a hashable form
    key_parts = [method]
    for arg in args:
        if isinstance(arg, (str, int, float, bool, type(None))):
            key_parts.append(str(arg))
        else:
            key_parts.append(str(type(arg).__name__))
    for k, v in sorted(kwargs.items()):
        if isinstance(v, (str, int, float, bool, type(None))):
            key_parts.append(f"{k}={v}")
    return "|".join(key_parts)


def clear_request_cache():
    """Clear the request cache. Call this between different stock analyses."""
    global _request_cache
    _request_cache.clear()


# Import from vendor-specific modules
from .local import get_YFin_data, get_finnhub_news, get_finnhub_company_insider_sentiment, get_finnhub_company_insider_transactions, get_simfin_balance_sheet, get_simfin_cashflow, get_simfin_income_statements, get_reddit_global_news, get_reddit_company_news
from .y_finance import get_YFin_data_online, get_stock_stats_indicators_window, get_balance_sheet as get_yfinance_balance_sheet, get_cashflow as get_yfinance_cashflow, get_income_statement as get_yfinance_income_statement, get_insider_transactions as get_yfinance_insider_transactions, get_fundamentals as get_yfinance_fundamentals, get_analyst_recommendations as get_yfinance_analyst_recommendations, get_earnings_data as get_yfinance_earnings_data, get_institutional_holders as get_yfinance_institutional_holders, get_yfinance_news as get_yfinance_news_feed, get_analyst_sentiment as get_yfinance_analyst_sentiment, get_sector_performance as get_yfinance_sector_performance, get_earnings_calendar as get_yfinance_earnings_calendar
from .google import get_google_news, get_google_global_news
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
from .jugaad_data import get_jugaad_stock_data, get_jugaad_indicators
from .markets import detect_market, Market, is_nifty_50_stock

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
            "get_analyst_recommendations",
            "get_earnings_data",
            "get_institutional_holders",
        ]
    },
    "news_data": {
        "description": "News (public/insiders, original/processed)",
        "tools": [
            "get_news",
            "get_global_news",
            "get_insider_sentiment",
            "get_insider_transactions",
            "get_earnings_calendar",
        ]
    },
    "social_sentiment_data": {
        "description": "Social sentiment and market perception",
        "tools": [
            "get_yfinance_news",
            "get_analyst_sentiment",
            "get_sector_performance",
        ]
    }
}

VENDOR_LIST = [
    "local",
    "yfinance",
    "openai",
    "google",
    "jugaad_data"
]

# Mapping of methods to their vendor-specific implementations
VENDOR_METHODS = {
    # core_stock_apis
    "get_stock_data": {
        "alpha_vantage": get_alpha_vantage_stock,
        "yfinance": get_YFin_data_online,
        "local": get_YFin_data,
        "jugaad_data": get_jugaad_stock_data,
    },
    # technical_indicators
    "get_indicators": {
        "alpha_vantage": get_alpha_vantage_indicator,
        "yfinance": get_stock_stats_indicators_window,
        "local": get_stock_stats_indicators_window,
        "jugaad_data": get_jugaad_indicators,
    },
    # fundamental_data
    "get_fundamentals": {
        "yfinance": get_yfinance_fundamentals,
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
        "google": get_google_global_news,
        "openai": get_global_news_openai,
        "local": get_reddit_global_news,
    },
    "get_insider_sentiment": {
        "local": get_finnhub_company_insider_sentiment
    },
    "get_insider_transactions": {
        "alpha_vantage": get_alpha_vantage_insider_transactions,
        "yfinance": get_yfinance_insider_transactions,
        "local": get_finnhub_company_insider_transactions,
    },
    # New fundamental tools
    "get_analyst_recommendations": {
        "yfinance": get_yfinance_analyst_recommendations,
    },
    "get_earnings_data": {
        "yfinance": get_yfinance_earnings_data,
    },
    "get_institutional_holders": {
        "yfinance": get_yfinance_institutional_holders,
    },
    # New social sentiment tools
    "get_yfinance_news": {
        "yfinance": get_yfinance_news_feed,
    },
    "get_analyst_sentiment": {
        "yfinance": get_yfinance_analyst_sentiment,
    },
    "get_sector_performance": {
        "yfinance": get_yfinance_sector_performance,
    },
    # New news tool
    "get_earnings_calendar": {
        "yfinance": get_yfinance_earnings_calendar,
    },
}

def get_category_for_method(method: str) -> str:
    """Get the category that contains the specified method."""
    for category, info in TOOLS_CATEGORIES.items():
        if method in info["tools"]:
            return category
    raise ValueError(f"Method '{method}' not found in any category")

def get_vendor(category: str, method: str = None, symbol: str = None) -> str:
    """Get the configured vendor for a data category or specific tool method.
    Tool-level configuration takes precedence over category-level.
    For NSE stocks, automatically routes to jugaad_data for core_stock_apis and technical_indicators.

    Args:
        category: Data category (e.g., "core_stock_apis", "technical_indicators")
        method: Specific tool method name
        symbol: Stock symbol (used for market detection)

    Returns:
        Vendor name string
    """
    config = get_config()

    # Check tool-level configuration first (if method provided)
    if method:
        tool_vendors = config.get("tool_vendors", {})
        if method in tool_vendors:
            return tool_vendors[method]

    # Market-aware vendor routing for NSE stocks
    if symbol:
        market_config = config.get("market", "auto")
        market = detect_market(symbol, market_config)

        if market == Market.INDIA_NSE:
            # Use yfinance as primary for NSE stocks (more reliable than jugaad_data from outside India)
            # jugaad_data requires direct NSE access which may be blocked/slow
            if category in ("core_stock_apis", "technical_indicators"):
                return "yfinance"  # yfinance handles .NS suffix automatically
            # Use yfinance for fundamentals (with .NS suffix handled in y_finance.py)
            elif category == "fundamental_data":
                return "yfinance"
            # Use google for news (handled in google.py with company name enhancement)
            elif category == "news_data":
                return "google"

    # Fall back to category-level configuration
    return config.get("data_vendors", {}).get(category, "default")

def route_to_vendor(method: str, *args, **kwargs):
    """Route method calls to appropriate vendor implementation with fallback support."""
    # Check cache first to avoid redundant API calls
    cache_key = _make_cache_key(method, args, kwargs)
    if cache_key in _request_cache:
        add_log("data", "data_fetch", f"📦 {method}({', '.join(str(a) for a in args)}) — cached")
        return _request_cache[cache_key]

    fetch_start = _time.time()
    args_str = ', '.join(str(a) for a in args)
    add_log("data", "data_fetch", f"🔄 Fetching {method}({args_str})...")

    category = get_category_for_method(method)

    # Extract symbol from args/kwargs for market-aware routing
    symbol = None
    if args:
        # First argument is typically the symbol/ticker
        symbol = args[0]
    elif "symbol" in kwargs:
        symbol = kwargs["symbol"]
    elif "ticker" in kwargs:
        symbol = kwargs["ticker"]
    elif "query" in kwargs:
        # For news queries, the query might be the symbol
        symbol = kwargs["query"]

    vendor_config = get_vendor(category, method, symbol)

    # Handle comma-separated vendors
    primary_vendors = [v.strip() for v in vendor_config.split(',')]

    if method not in VENDOR_METHODS:
        raise ValueError(f"Method '{method}' not supported")

    # Get all available vendors for this method for fallback
    all_available_vendors = list(VENDOR_METHODS[method].keys())
    
    # Create fallback vendor list: primary vendors first, then remaining vendors as fallbacks
    fallback_vendors = primary_vendors.copy()
    for vendor in all_available_vendors:
        if vendor not in fallback_vendors:
            fallback_vendors.append(vendor)

    # Debug: Print fallback ordering
    primary_str = " → ".join(primary_vendors)
    fallback_str = " → ".join(fallback_vendors)
    _debug_print(f"DEBUG: {method} - Primary: [{primary_str}] | Full fallback order: [{fallback_str}]")

    # Track results and execution state
    results = []
    vendor_attempt_count = 0
    any_primary_vendor_attempted = False
    successful_vendor = None

    for vendor in fallback_vendors:
        if vendor not in VENDOR_METHODS[method]:
            if vendor in primary_vendors:
                _debug_print(f"INFO: Vendor '{vendor}' not supported for method '{method}', falling back to next vendor")
            continue

        vendor_impl = VENDOR_METHODS[method][vendor]
        is_primary_vendor = vendor in primary_vendors
        vendor_attempt_count += 1

        # Track if we attempted any primary vendor
        if is_primary_vendor:
            any_primary_vendor_attempted = True

        # Debug: Print current attempt
        vendor_type = "PRIMARY" if is_primary_vendor else "FALLBACK"
        _debug_print(f"DEBUG: Attempting {vendor_type} vendor '{vendor}' for {method} (attempt #{vendor_attempt_count})")

        # Handle list of methods for a vendor
        if isinstance(vendor_impl, list):
            vendor_methods = [(impl, vendor) for impl in vendor_impl]
            _debug_print(f"DEBUG: Vendor '{vendor}' has multiple implementations: {len(vendor_methods)} functions")
        else:
            vendor_methods = [(vendor_impl, vendor)]

        # Run methods for this vendor
        vendor_results = []
        for impl_func, vendor_name in vendor_methods:
            try:
                _debug_print(f"DEBUG: Calling {impl_func.__name__} from vendor '{vendor_name}'...")
                result = impl_func(*args, **kwargs)
                vendor_results.append(result)
                _debug_print(f"SUCCESS: {impl_func.__name__} from vendor '{vendor_name}' completed successfully")
                    
            except AlphaVantageRateLimitError as e:
                if vendor == "alpha_vantage":
                    _debug_print(f"RATE_LIMIT: Alpha Vantage rate limit exceeded, falling back to next available vendor")
                    _debug_print(f"DEBUG: Rate limit details: {e}")
                # Continue to next vendor for fallback
                continue
            except Exception as e:
                # Log error but continue with other implementations
                _debug_print(f"FAILED: {impl_func.__name__} from vendor '{vendor_name}' failed: {e}")
                continue

        # Add this vendor's results
        if vendor_results:
            results.extend(vendor_results)
            successful_vendor = vendor
            result_summary = f"Got {len(vendor_results)} result(s)"
            _debug_print(f"SUCCESS: Vendor '{vendor}' succeeded - {result_summary}")
            
            # Stopping logic: Stop after first successful vendor for single-vendor configs
            # Multiple vendor configs (comma-separated) may want to collect from multiple sources
            if len(primary_vendors) == 1:
                _debug_print(f"DEBUG: Stopping after successful vendor '{vendor}' (single-vendor config)")
                break
        else:
            _debug_print(f"FAILED: Vendor '{vendor}' produced no results")

    # Final result summary
    if not results:
        _debug_print(f"FAILURE: All {vendor_attempt_count} vendor attempts failed for method '{method}'")
        raise RuntimeError(f"All vendor implementations failed for method '{method}'")
    else:
        _debug_print(f"FINAL: Method '{method}' completed with {len(results)} result(s) from {vendor_attempt_count} vendor attempt(s)")

    # Return single result if only one, otherwise concatenate as string
    if len(results) == 1:
        final_result = results[0]
    else:
        # Convert all results to strings and concatenate
        final_result = '\n'.join(str(result) for result in results)

    # Cache the result for subsequent calls
    _request_cache[cache_key] = final_result

    fetch_elapsed = _time.time() - fetch_start
    result_len = len(str(final_result))
    result_preview = str(final_result)[:200].replace('\n', ' ')
    add_log("data", "data_fetch", f"✅ {method}({args_str}) → {result_len} chars in {fetch_elapsed:.1f}s via {successful_vendor} | {result_preview}...")

    # Capture raw data for frontend debugging
    raw_data_store.log_fetch(
        method=method,
        symbol=str(symbol) if symbol else "",
        vendor=str(successful_vendor) if successful_vendor else "unknown",
        raw_data=str(final_result),
        args_str=args_str,
        duration_s=fetch_elapsed,
    )

    return final_result