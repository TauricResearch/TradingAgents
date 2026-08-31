"""
Execution Layer for TradingAgents.

Provides order execution across multiple markets (crypto, stocks, options, futures).
"""

from .base import (
    ExecutionProvider,
    OrderRequest,
    OrderResult,
    OrderSide,
    OrderStatus,
    OrderType,
)
from .ccxt_provider import CCXTProvider, get_ccxt_provider
from .lumibot_provider import LumibotProvider, get_lumibot_provider
from .registry import (
    get_provider,
    get_all_providers,
    get_providers_for_market,
    register_provider,
    init_default_providers,
)

__all__ = [
    "ExecutionProvider",
    "OrderRequest",
    "OrderResult",
    "OrderSide",
    "OrderStatus",
    "OrderType",
    "CCXTProvider",
    "get_ccxt_provider",
    "LumibotProvider",
    "get_lumibot_provider",
    "get_provider",
    "get_all_providers",
    "get_providers_for_market",
    "register_provider",
    "init_default_providers",
]
