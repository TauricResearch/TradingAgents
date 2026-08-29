"""
Provider registry and factory.

Centralizes provider management and provides a unified interface
for accessing data from multiple sources.
"""

from typing import Optional

from .base import DataProvider
from .yahoo import YahooProvider
from .byma import BYMAProvider
from .worldmonitor import WorldMonitorProvider
from .document_extractor import DocumentExtractionProvider


# Global provider registry
_PROVIDERS: dict[str, DataProvider] = {}


def register_provider(provider: DataProvider) -> None:
    """Register a data provider."""
    _PROVIDERS[provider.name] = provider


def get_provider(name: str) -> Optional[DataProvider]:
    """Get a registered provider by name."""
    return _PROVIDERS.get(name)


def get_all_providers() -> dict[str, DataProvider]:
    """Get all registered providers."""
    return _PROVIDERS.copy()


def get_providers_for_market(market: str) -> list[DataProvider]:
    """Get all providers that support a specific market."""
    return [
        p for p in _PROVIDERS.values()
        if p.has_market(market)
    ]


def init_default_providers() -> None:
    """Initialize and register all default providers."""
    register_provider(YahooProvider())
    register_provider(BYMAProvider())
    register_provider(WorldMonitorProvider())
    register_provider(DocumentExtractionProvider())


# Auto-initialize on import
init_default_providers()
