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
from .cls_news import get_news_cls
from .cninfo_disclosures import get_disclosures_cninfo
from .eastmoney_news import get_news_eastmoney

# Configuration and routing logic
from .config import get_config
from .dataflow_cache import (
    cached_call as _cached_call,
    is_cacheable as _is_cacheable,
    vendor_cached_call as _vendor_cached_call,
)

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
        # Chinese-language news for HK / Shanghai / Shenzhen counters.
        "eastmoney": get_news_eastmoney,
        # CLS flash-news stream — adds real-time market-moving headlines
        # alongside Eastmoney's editorial coverage. HK/SH/SZ.
        "cls": get_news_cls,
        # Cninfo regulatory filings — official CSRC disclosures. SH/SZ only.
        "cninfo": get_disclosures_cninfo,
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

def _resolve_auto_vendors(method: str, args: tuple) -> list:
    """Pick the concrete vendor list when the user configures ``"auto"``.

    Returns a list because Asian-market tickers are now multi-sourced:
    Eastmoney (editorial), CLS (flash news), and Cninfo (regulatory
    filings, SH/SZ only) get merged into one Markdown blob the analyst
    sees as a single tool result. ``route_to_vendor`` walks this list
    in order, calls each vendor, and concatenates non-empty results;
    a single per-vendor failure does not abort the whole fetch.

    Mapping by ticker suffix:
      * ``.SS`` / ``.SZ`` → ``eastmoney`` + ``cls`` + ``cninfo``
      * ``.HK``           → ``eastmoney`` + ``cls``
      * everything else   → ``yfinance``

    Returns ``["yfinance"]`` for ``get_global_news`` regardless of args
    (no ticker to dispatch on).
    """
    single = ["yfinance"]
    if method == "get_global_news":
        return single
    if not args:
        return single
    ticker = str(args[0])
    if "." not in ticker:
        return single
    suffix = ticker.rsplit(".", 1)[1].upper()
    # ``.SH`` is the same exchange as ``.SS`` — different platforms use either
    # convention for Shanghai. Normalise here so users can paste tickers from
    # any source.
    if suffix in ("SS", "SH", "SZ"):
        return ["eastmoney", "cls", "cninfo"]
    if suffix == "HK":
        return ["eastmoney", "cls"]
    return single


# Back-compat for any external code that still imports the singular form.
def _resolve_auto_vendor(method: str, args: tuple) -> str:
    """Deprecated single-vendor variant. Returns the first auto-resolved vendor."""
    return _resolve_auto_vendors(method, args)[0]


def route_to_vendor(method: str, *args, **kwargs):
    """Route method calls to appropriate vendor implementation with fallback support.

    Cacheable methods (global news, financial statements) go through the
    on-disk dataflow cache so multiple tickers analysed the same day or
    repeat analyses of the same ticker within a quarter avoid the network
    fetch entirely. Cache misses fall through to the live vendor call.

    When ``data_vendors[category]`` is set to ``"auto"``, the news methods
    additionally dispatch by ticker suffix (HK / SS / SZ → Eastmoney,
    else yfinance) so multi-market workflows pick the right Chinese-vs-
    English source automatically.
    """
    if method not in VENDOR_METHODS:
        raise ValueError(f"Method '{method}' not supported")

    def _call_vendor(vendor: str):
        vendor_impl = VENDOR_METHODS[method][vendor]
        impl_func = vendor_impl[0] if isinstance(vendor_impl, list) else vendor_impl
        return impl_func(*args, **kwargs)

    def _call_vendor_cached(vendor: str):
        """Call ``vendor`` for ``method``, caching per-vendor when the news
        method has a stable cache key. Multiple analyses of the same ticker
        in the same day reuse the fetch; multiple HK/CN tickers in the
        same day reuse the parts of the merge that aren't ticker-specific
        (Cninfo is per-ticker but per-week, so the same ticker any day this
        week reuses)."""
        return _vendor_cached_call(
            vendor, method, args, kwargs, lambda: _call_vendor(vendor)
        )

    def _fetch():
        category = get_category_for_method(method)
        vendor_config = get_vendor(category, method)
        if vendor_config == "auto":
            primary_vendors = _resolve_auto_vendors(method, args)
        else:
            primary_vendors = [v.strip() for v in vendor_config.split(',')]

        # Multi-source merge: when auto resolves >1 vendor (e.g. HK / SH / SZ
        # tickers fan out to Eastmoney + CLS + Cninfo), call each vendor and
        # concatenate non-empty results. A per-vendor failure does not abort
        # the whole fetch — the analyst sees whichever sources succeeded.
        # Each vendor's call is cached independently so a re-run reuses
        # whichever sources are already hot.
        if len(primary_vendors) > 1:
            blocks = []
            for vendor in primary_vendors:
                if vendor not in VENDOR_METHODS[method]:
                    continue
                try:
                    out = _call_vendor_cached(vendor)
                except Exception as e:
                    logger.warning("Vendor %s failed for %s: %s", vendor, method, e)
                    continue
                if isinstance(out, str) and out.strip():
                    # Skip pure skip-markers like "[CLS skip — ... not covered]"
                    # so downstream prompts aren't padded with no-op noise.
                    stripped = out.strip()
                    if stripped.startswith("[") and "skip" in stripped.lower() and stripped.endswith("]"):
                        continue
                    blocks.append(out)
            if not blocks:
                # All sources empty/failed: fall through to legacy fallback.
                primary_vendors = ["yfinance"]
            else:
                return "\n\n---\n\n".join(blocks)

        all_available_vendors = list(VENDOR_METHODS[method].keys())
        fallback_vendors = list(primary_vendors)
        for vendor in all_available_vendors:
            if vendor not in fallback_vendors:
                fallback_vendors.append(vendor)

        for vendor in fallback_vendors:
            if vendor not in VENDOR_METHODS[method]:
                continue
            try:
                return _call_vendor_cached(vendor)
            except AlphaVantageRateLimitError:
                continue  # Only rate limits trigger fallback
        raise RuntimeError(f"No available vendor for '{method}'")

    if _is_cacheable(method):
        return _cached_call(method, args, kwargs, _fetch)
    return _fetch()
