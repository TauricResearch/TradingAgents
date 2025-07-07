from .search_provider import (
    SearchProvider,
    GoogleSearchProvider,
    OpenAISearchProvider
)
import hashlib
import json


class SearchProviderFactory:
    _cache = {}  # 클래스 레벨 캐시
    
    @staticmethod
    def create_provider(config: dict[str, any]) -> SearchProvider:
        """
        Create a SearchProvider with caching to avoid creating new instances.
        Uses config hash as cache key for efficient reuse.
        """
        # Create cache key from relevant config values
        cache_key_data = {
            "backend_url": config["backend_url"],
            "model": config["quick_think_llm"]
        }
        cache_key = hashlib.md5(json.dumps(cache_key_data, sort_keys=True).encode()).hexdigest()
        
        # Return cached instance if exists
        if cache_key in SearchProviderFactory._cache:
            return SearchProviderFactory._cache[cache_key]
        
        # Create new instance
        backend_url = config["backend_url"]
        model = config["quick_think_llm"]

        if "generativelanguage.googleapis.com" in backend_url:
            provider = GoogleSearchProvider(model)
        else:
            provider = OpenAISearchProvider(model, backend_url)
        
        # Cache and return
        SearchProviderFactory._cache[cache_key] = provider
        return provider
    
    @staticmethod
    def clear_cache():
        """Clear the provider cache (useful for testing or config changes)."""
        SearchProviderFactory._cache.clear()

