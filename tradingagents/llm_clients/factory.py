import warnings
from typing import Optional

from .base_client import BaseLLMClient
from .openai_client import OpenAIClient
from .anthropic_client import AnthropicClient
from .google_client import GoogleClient
from .config_loader import load_config, get_config_section

DEFAULT_PROVIDER_TYPES: dict[str, str] = {
    "openai": "openai",
    "anthropic": "anthropic",
    "google": "google",
    "xai": "openai",
    "openrouter": "openai",
    "ollama": "openai",
    "lmstudio": "openai",
}


def _load_provider_types() -> dict[str, str]:
    try:
        config = load_config()
        provider_types = get_config_section(config, "LLM_PROVIDER_TYPES", dict)
        return {
            str(name).lower(): str(client_type).lower()
            for name, client_type in provider_types.items()
        }
    except RuntimeError as exc:
        warnings.warn(
            f"Failed to load LLM_PROVIDER_TYPES from config.json: {exc}. "
            "Using built-in provider mapping.",
            RuntimeWarning,
            stacklevel=2,
        )
        return DEFAULT_PROVIDER_TYPES.copy()


_PROVIDER_TYPES: dict[str, str] | None = None


def _get_provider_types() -> dict[str, str]:
    global _PROVIDER_TYPES
    if _PROVIDER_TYPES is None:
        _PROVIDER_TYPES = _load_provider_types()
    return _PROVIDER_TYPES


def create_llm_client(
    provider: str,
    model: str,
    base_url: Optional[str] = None,
    **kwargs,
) -> BaseLLMClient:
    """Create an LLM client for the specified provider.

    Args:
        provider: LLM provider (openai, anthropic, google, xai, ollama, openrouter)
        model: Model name/identifier
        base_url: Optional base URL for API endpoint
        **kwargs: Additional provider-specific arguments
            - http_client: Custom httpx.Client for SSL proxy or certificate customization
            - http_async_client: Custom httpx.AsyncClient for async operations
            - timeout: Request timeout in seconds
            - max_retries: Maximum retry attempts
            - api_key: API key for the provider
            - callbacks: LangChain callbacks

    Returns:
        Configured BaseLLMClient instance

    Raises:
        ValueError: If provider is not supported
    """
    provider_lower = provider.lower()
    provider_type = _get_provider_types().get(provider_lower)

    if provider_type == "openai":
        return OpenAIClient(model, base_url, provider=provider_lower, **kwargs)

    if provider_type == "anthropic":
        return AnthropicClient(model, base_url, **kwargs)

    if provider_type == "google":
        return GoogleClient(model, base_url, **kwargs)

    raise ValueError(f"Unsupported LLM provider: {provider}")
