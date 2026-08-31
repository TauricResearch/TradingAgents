"""
Execution registry and factory.

Centralizes execution provider management and provides a unified interface
for order execution across different markets.
"""

from typing import Optional

from .base import ExecutionProvider
from .ccxt_provider import CCXTProvider
from .lumibot_provider import LumibotProvider


# Global execution provider registry
_PROVIDERS: dict[str, ExecutionProvider] = {}


def register_provider(provider: ExecutionProvider) -> None:
    """Register an execution provider."""
    _PROVIDERS[provider.name] = provider


def get_provider(name: str) -> Optional[ExecutionProvider]:
    """Get a registered provider by name."""
    return _PROVIDERS.get(name)


def get_all_providers() -> dict[str, ExecutionProvider]:
    """Get all registered providers."""
    return _PROVIDERS.copy()


def get_providers_for_market(market: str) -> list[ExecutionProvider]:
    """Get all providers that support a specific market."""
    return [
        p for p in _PROVIDERS.values()
        if p.has_market(market)
    ]


def init_default_providers() -> None:
    """Initialize and register all default providers."""
    register_provider(CCXTProvider())
    register_provider(LumibotProvider())


# Auto-initialize on import
init_default_providers()
