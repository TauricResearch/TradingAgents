"""Vendor routing for data tools.

Phase 0 (equity strip) replaced this module's contents with a stub. The
crypto + Kalshi data layer is built up in Phase 1 — see
``tradingagents/dataflows/coinbase.py``, ``kalshi_market.py``,
``crypto_news.py``, ``reddit_sentiment.py``, ``cmc_sentiment.py``,
``onchain.py``.

The vendor-routing pattern (one logical tool name dispatched to a
configured provider implementation) is preserved so multiple sources
can back the same analyst tool. Tool registration happens in Phase 1.
"""

from typing import Callable, Dict

from .config import get_config


# Tools organized by category. Phase 1 populates each list with the
# crypto/Kalshi tool names actually wired into analyst tool nodes.
TOOLS_CATEGORIES: Dict[str, Dict] = {
    "crypto_price": {
        "description": "Spot OHLCV / orderbook data for crypto assets",
        "tools": [],
    },
    "kalshi_market": {
        "description": "Kalshi contract metadata, YES/NO mid-price, trade history",
        "tools": [],
    },
    "crypto_news": {
        "description": "Crypto financial news aggregation",
        "tools": [],
    },
    "sentiment": {
        "description": "Reddit + CoinMarketCap community sentiment",
        "tools": [],
    },
    "on_chain": {
        "description": "Blockchain-native metrics: flows, mempool, ETF custody",
        "tools": [],
    },
}

VENDOR_LIST: list = []

# Method name -> {vendor_name: callable}. Populated in Phase 1.
VENDOR_METHODS: Dict[str, Dict[str, Callable]] = {}


def get_category_for_method(method: str) -> str:
    for category, info in TOOLS_CATEGORIES.items():
        if method in info["tools"]:
            return category
    raise ValueError(f"Method '{method}' not found in any category")


def get_vendor(category: str, method: str = None) -> str:
    config = get_config()
    if method:
        tool_vendors = config.get("tool_vendors", {})
        if method in tool_vendors:
            return tool_vendors[method]
    return config.get("data_vendors", {}).get(category, "default")


def route_to_vendor(method: str, *args, **kwargs):
    """Route a logical tool call to the configured vendor implementation.

    Phase 1 will register vendor implementations in ``VENDOR_METHODS``.
    """
    if method not in VENDOR_METHODS:
        raise NotImplementedError(
            f"Tool '{method}' has no registered vendor implementations. "
            "Phase 1 (data layer) will populate VENDOR_METHODS."
        )

    category = get_category_for_method(method)
    vendor_config = get_vendor(category, method)
    primary_vendors = [v.strip() for v in vendor_config.split(",")]

    all_available = list(VENDOR_METHODS[method].keys())
    fallback_vendors = primary_vendors.copy()
    for vendor in all_available:
        if vendor not in fallback_vendors:
            fallback_vendors.append(vendor)

    last_error = None
    for vendor in fallback_vendors:
        if vendor not in VENDOR_METHODS[method]:
            continue
        impl = VENDOR_METHODS[method][vendor]
        try:
            return impl(*args, **kwargs)
        except Exception as e:  # pragma: no cover — Phase 1 will refine fallback
            last_error = e
            continue

    if last_error is not None:
        raise last_error
    raise RuntimeError(f"No available vendor for '{method}'")
