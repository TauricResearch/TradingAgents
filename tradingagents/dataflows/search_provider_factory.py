from .search_provider import SearchProvider
import hashlib
import json
from typing import Dict, Callable, Any
from abc import ABC, abstractmethod


class ProviderSelector(ABC):
    """Abstract base class for provider selection strategies."""
    
    @abstractmethod
    def select_provider_type(self, config: Dict[str, Any]) -> str:
        """Select provider type based on configuration."""
        pass


class MappingBasedProviderSelector(ProviderSelector):
    """Selects provider based on URL pattern mapping table."""
    
    def __init__(self, mappings: Dict[str, str], default_provider: str = "openai"):
        self._mappings = mappings
        self._default_provider = default_provider
    
    def select_provider_type(self, config: Dict[str, Any]) -> str:
        backend_url = config.get("backend_url", "")
        for pattern, provider_type in self._mappings.items():
            if pattern in backend_url:
                return provider_type
        return self._default_provider


class SearchProviderRegistry:
    """Registry for search provider creation functions."""
    
    def __init__(self):
        self._providers: Dict[str, Callable[[Dict[str, Any]], SearchProvider]] = {}
    
    def register(self, provider_type: str, creator: Callable[[Dict[str, Any]], SearchProvider]):
        """Register a provider creator function."""
        self._providers[provider_type] = creator
    
    def create(self, provider_type: str, config: Dict[str, Any]) -> SearchProvider:
        """Create a provider instance using registered creator."""
        if provider_type not in self._providers:
            raise ValueError(f"Unknown provider type: {provider_type}")
        return self._providers[provider_type](config)
    
    def get_available_types(self) -> list[str]:
        """Get list of available provider types."""
        return list(self._providers.keys())


class SearchProviderFactoryImpl:
    """Enhanced factory for creating SearchProvider instances with caching and extensibility."""
    
    def __init__(self, registry: SearchProviderRegistry, selector: ProviderSelector):
        self._registry = registry
        self._selector = selector
        self._cache: Dict[str, SearchProvider] = {}
    
    def create_provider(self, config: Dict[str, Any]) -> SearchProvider:
        """
        Create a SearchProvider with caching to avoid creating new instances.
        Uses config hash as cache key for efficient reuse.
        """
        # Create cache key from relevant config values
        cache_key_data = {
            "backend_url": config.get("backend_url", ""),
            "model": config.get("quick_think_llm", "")
        }
        cache_key = hashlib.md5(json.dumps(cache_key_data, sort_keys=True).encode()).hexdigest()
        
        # Return cached instance if exists
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # Select and create provider
        provider_type = self._selector.select_provider_type(config)
        provider = self._registry.create(provider_type, config)
        
        # Cache and return
        self._cache[cache_key] = provider
        return provider
    
    def clear_cache(self):
        """Clear the provider cache (useful for testing or config changes)."""
        self._cache.clear()
    
    def get_available_provider_types(self) -> list[str]:
        """Get list of available provider types."""
        return self._registry.get_available_types()


def create_search_provider_factory() -> SearchProviderFactoryImpl:
    """Create a configured SearchProviderFactory with default providers."""
    registry = SearchProviderRegistry()
    
    # Register default providers
    def create_google_provider(config: Dict[str, Any]) -> SearchProvider:
        from .search_provider import GoogleSearchProvider
        return GoogleSearchProvider(config["quick_think_llm"])
    
    def create_openai_provider(config: Dict[str, Any]) -> SearchProvider:
        from .search_provider import OpenAISearchProvider
        return OpenAISearchProvider(config["quick_think_llm"], config["backend_url"])
    
    registry.register("google", create_google_provider)
    registry.register("openai", create_openai_provider)
    
    # Create URL pattern mappings (easily extensible)
    url_mappings = {
        "generativelanguage.googleapis.com": "google",
        "api.openai.com": "openai",
    }
    
    selector = MappingBasedProviderSelector(url_mappings, default_provider="openai")
    return SearchProviderFactoryImpl(registry, selector)


# Backward compatibility - singleton instance
_default_factory = create_search_provider_factory()


class SearchProviderFactory:
    """Backward compatibility wrapper for the old static factory."""
    
    @staticmethod
    def create_provider(config: Dict[str, Any]) -> SearchProvider:
        return _default_factory.create_provider(config)
    
    @staticmethod
    def clear_cache():
        _default_factory.clear_cache()