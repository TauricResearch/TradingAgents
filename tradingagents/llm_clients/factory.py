import json
from pathlib import Path
from typing import Optional

from .base_client import BaseLLMClient
from .openai_client import OpenAIClient
from .anthropic_client import AnthropicClient
from .google_client import GoogleClient

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.json"


def _load_config() -> dict:
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as config_file:
            config = json.load(config_file)
    except FileNotFoundError as exc:
        raise RuntimeError(f"Config file not found: {CONFIG_PATH}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON in config file: {CONFIG_PATH}") from exc
    except OSError as exc:
        raise RuntimeError(f"Unable to read config file: {CONFIG_PATH}") from exc
    if not isinstance(config, dict):
        raise RuntimeError(f"Invalid config format in file: {CONFIG_PATH}")
    return config


def _load_provider_types() -> dict[str, str]:
    provider_types = _load_config().get("LLM_PROVIDER_TYPES")
    if not isinstance(provider_types, dict):
        raise RuntimeError(
            f"Invalid or missing 'LLM_PROVIDER_TYPES' in config file: {CONFIG_PATH}"
        )
    return {
        str(name).lower(): str(client_type).lower()
        for name, client_type in provider_types.items()
    }


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
