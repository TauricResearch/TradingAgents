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
from .utils import safe_ticker_component

# Configuration and routing logic
from .config import get_config

import logging
_logger = logging.getLogger(__name__)

# Methods whose first positional argument is a ticker symbol.
# These are validated with safe_ticker_component before dispatch.
_TICKER_FIRST_METHODS = frozenset({
    "get_stock_data",
    "get_indicators",
    "get_fundamentals",
    "get_balance_sheet",
    "get_cashflow",
    "get_income_statement",
    "get_news",
    "get_insider_transactions",
})

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
}

import os
import json
import time
import threading
from pathlib import Path

class APICache:
    _lock = threading.Lock()

    @classmethod
    def get_cache_path(cls) -> Path:
        config = get_config()
        cache_dir = Path(config.get("data_cache_dir", os.path.join(os.path.expanduser("~"), ".tradingagents", "cache")))
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir / "api_cache.json"

    @classmethod
    def load_cache(cls) -> dict:
        path = cls.get_cache_path()
        if not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            _logger.warning("API cache file corrupted or unreadable (%s), starting fresh: %s", path, e)
            return {}

    @classmethod
    def save_cache(cls, cache_data: dict) -> None:
        path = cls.get_cache_path()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, indent=4)
        except Exception as e:
            _logger.warning("Failed to save API cache to %s: %s", path, e)

    @classmethod
    def get_ttl(cls, method: str) -> float:
        try:
            category = get_category_for_method(method)
        except ValueError:
            return 3600.0

        if category == "core_stock_apis" or category == "technical_indicators":
            return 600.0  # 10 minutes
        elif category == "fundamental_data":
            return 43200.0  # 12 hours
        elif category == "news_data":
            return 1800.0  # 30 minutes
        return 3600.0

    @classmethod
    def get(cls, method: str, *args, **kwargs):
        key = f"{method}:{json.dumps(args, sort_keys=True)}:{json.dumps(kwargs, sort_keys=True)}"
        with cls._lock:
            cache = cls.load_cache()
            entry = cache.get(key)
            if entry:
                timestamp = entry.get("timestamp", 0)
                ttl = cls.get_ttl(method)
                if time.time() - timestamp < ttl:
                    return entry.get("data")
        return None

    @classmethod
    def set(cls, method: str, data, *args, **kwargs) -> None:
        key = f"{method}:{json.dumps(args, sort_keys=True)}:{json.dumps(kwargs, sort_keys=True)}"
        with cls._lock:
            cache = cls.load_cache()
            cache[key] = {
                "timestamp": time.time(),
                "data": data
            }
            now = time.time()
            pruned_cache = {
                k: v for k, v in cache.items()
                if now - v.get("timestamp", 0) < 86400.0
            }
            cls.save_cache(pruned_cache)


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
    # Validate ticker symbol for methods where first arg is a ticker.
    # Tickers flow from LLM tool calls which can be influenced by prompt injection
    # in fetched external content (news, filings, etc.).
    if method in _TICKER_FIRST_METHODS and args:
        safe_ticker_component(args[0])

    cached_val = APICache.get(method, *args, **kwargs)
    if cached_val is not None:
        return cached_val

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
            val = impl_func(*args, **kwargs)
            APICache.set(method, val, *args, **kwargs)
            return val
        except AlphaVantageRateLimitError:
            continue  # Only rate limits trigger fallback

    raise RuntimeError(f"No available vendor for '{method}'")