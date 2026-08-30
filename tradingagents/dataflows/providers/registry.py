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

try:
    from .markitdown_provider import MarkItDownProvider

    _HAS_MARKITDOWN_PROVIDER = True
except Exception:  # noqa: BLE001
    MarkItDownProvider = None  # type: ignore
    _HAS_MARKITDOWN_PROVIDER = False


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


# MarkItDown singleton (document ingestion, not a DataProvider)
_markitdown_singleton = None


def get_markitdown_provider(llm_client=None, enable_llm_image: bool = False):  # type: ignore[no-untyped-def]
    """Return shared MarkItDownProvider; creates on first call.

    Used by the fundamentals analyst for BCRA/BYMA PDFs, FRED docs, balance sheets.
    Gracefully returns a fallback provider when markitdown is not installed.
    """
    global _markitdown_singleton
    if _markitdown_singleton is not None and llm_client is None:
        return _markitdown_singleton
    if not _HAS_MARKITDOWN_PROVIDER or MarkItDownProvider is None:
        return None
    provider = MarkItDownProvider(llm_client=llm_client, enable_llm_image=enable_llm_image)
    if llm_client is None:
        _markitdown_singleton = provider
    return provider


# Auto-initialize on import
init_default_providers()
