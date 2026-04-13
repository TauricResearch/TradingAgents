from dataclasses import dataclass
from typing import Annotated, Any

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

# Lazy china_data import — only fails at runtime if akshare is missing and china_data vendor is selected
try:
    from .china_data import (
        get_china_data_online,
        get_indicators_china,
        get_china_stock_info,
        get_china_financials,
        get_china_news,
        get_china_market_news,
        # Wrappers matching caller signatures:
        get_china_fundamentals,
        get_china_balance_sheet,
        get_china_cashflow,
        get_china_income_statement,
        get_china_news_wrapper,
        get_china_global_news_wrapper,
        get_china_insider_transactions,
    )
    _china_data_available = True
except (ImportError, AttributeError):
    _china_data_available = False
    get_china_data_online = None
    get_indicators_china = None
    get_china_stock_info = None
    get_china_financials = None
    get_china_news = None
    get_china_market_news = None
    get_china_fundamentals = None
    get_china_balance_sheet = None
    get_china_cashflow = None
    get_china_income_statement = None
    get_china_news_wrapper = None
    get_china_global_news_wrapper = None
    get_china_insider_transactions = None


# Configuration and routing logic
from .config import get_config

# Tools organized by category
TOOLS_CATEGORIES = {
    "core_stock_apis": {
        "description": "OHLCV stock price data",
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

VENDOR_LIST = [
    "yfinance",
    "alpha_vantage",
    *(["china_data"] if _china_data_available else []),
]

# Mapping of methods to their vendor-specific implementations
# china_data entries are only present if akshare is installed (_china_data_available)
_base_vendor_methods = {
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

# Conditionally add china_data vendor only if akshare is available
if _china_data_available:
    _base_vendor_methods["get_stock_data"]["china_data"] = get_china_data_online
    _base_vendor_methods["get_indicators"]["china_data"] = get_indicators_china
    _base_vendor_methods["get_fundamentals"]["china_data"] = get_china_fundamentals
    _base_vendor_methods["get_balance_sheet"]["china_data"] = get_china_balance_sheet
    _base_vendor_methods["get_cashflow"]["china_data"] = get_china_cashflow
    _base_vendor_methods["get_income_statement"]["china_data"] = get_china_income_statement
    _base_vendor_methods["get_news"]["china_data"] = get_china_news_wrapper
    _base_vendor_methods["get_global_news"]["china_data"] = get_china_global_news_wrapper
    _base_vendor_methods["get_insider_transactions"]["china_data"] = get_china_insider_transactions

VENDOR_METHODS = _base_vendor_methods
del _base_vendor_methods


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


@dataclass(frozen=True)
class VendorSelection:
    """Resolved vendor routing metadata for one dataflow method call."""

    method: str
    category: str
    configured_vendors: tuple[str, ...]
    fallback_chain: tuple[str, ...]


class DataflowAdapter:
    """Thin adapter boundary over legacy vendor routing logic."""

    def resolve(self, method: str) -> VendorSelection:
        category = get_category_for_method(method)
        vendor_config = get_vendor(category, method)
        configured_vendors = tuple(v.strip() for v in vendor_config.split(",") if v.strip())

        if method not in VENDOR_METHODS:
            raise ValueError(f"Method '{method}' not supported")

        all_available_vendors = list(VENDOR_METHODS[method].keys())
        fallback_chain = list(configured_vendors)
        for vendor in all_available_vendors:
            if vendor not in fallback_chain:
                fallback_chain.append(vendor)

        return VendorSelection(
            method=method,
            category=category,
            configured_vendors=configured_vendors,
            fallback_chain=tuple(fallback_chain),
        )

    def execute(self, method: str, *args: Any, **kwargs: Any):
        """Route the call through the configured vendor chain with legacy fallback behavior."""
        selection = self.resolve(method)

        for vendor in selection.fallback_chain:
            if vendor not in VENDOR_METHODS[method]:
                continue

            vendor_impl = VENDOR_METHODS[method][vendor]
            impl_func = vendor_impl[0] if isinstance(vendor_impl, list) else vendor_impl

            try:
                return impl_func(*args, **kwargs)
            except AlphaVantageRateLimitError:
                continue  # Only rate limits trigger fallback

        raise RuntimeError(f"No available vendor for '{method}'")


DEFAULT_DATAFLOW_ADAPTER = DataflowAdapter()


def route_to_vendor(method: str, *args, **kwargs):
    """Route method calls to appropriate vendor implementation with fallback support."""
    return DEFAULT_DATAFLOW_ADAPTER.execute(method, *args, **kwargs)
