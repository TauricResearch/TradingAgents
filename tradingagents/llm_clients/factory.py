from dataclasses import dataclass
from typing import Callable, Optional
import re

from .base_client import BaseLLMClient
from .openai_client import OpenAIClient
from .anthropic_client import AnthropicClient
from .google_client import GoogleClient
from .azure_client import AzureOpenAIClient

# Providers that use the OpenAI-compatible chat completions API
_OPENAI_COMPATIBLE = (
    "openai", "xai", "deepseek", "qwen", "glm", "ollama", "openrouter",
)


@dataclass(frozen=True)
class ProviderSpec:
    """Provider registry entry for LLM client creation.

    Attributes:
        canonical_name: Primary provider identifier
        aliases: Alternative names that resolve to this provider
        builder: Factory function to create the client instance
        base_url_patterns: Regex patterns for valid base URLs (None = no validation)
    """

    canonical_name: str
    aliases: tuple[str, ...]
    builder: Callable[..., BaseLLMClient]
    base_url_patterns: Optional[tuple[str, ...]] = None


_PROVIDER_SPECS: tuple[ProviderSpec, ...] = (
    ProviderSpec(
        canonical_name="openai",
        aliases=("openai",),
        builder=lambda model, base_url=None, **kwargs: OpenAIClient(
            model,
            base_url,
            provider="openai",
            **kwargs,
        ),
        base_url_patterns=(r"api\.openai\.com",),
    ),
    ProviderSpec(
        canonical_name="ollama",
        aliases=("ollama",),
        builder=lambda model, base_url=None, **kwargs: OpenAIClient(
            model,
            base_url,
            provider="ollama",
            **kwargs,
        ),
        base_url_patterns=(r"localhost:\d+", r"127\.0\.0\.1:\d+", r"ollama"),
    ),
    ProviderSpec(
        canonical_name="openrouter",
        aliases=("openrouter",),
        builder=lambda model, base_url=None, **kwargs: OpenAIClient(
            model,
            base_url,
            provider="openrouter",
            **kwargs,
        ),
        base_url_patterns=(r"openrouter\.ai",),
    ),
    ProviderSpec(
        canonical_name="xai",
        aliases=("xai",),
        builder=lambda model, base_url=None, **kwargs: OpenAIClient(
            model,
            base_url,
            provider="xai",
            **kwargs,
        ),
        base_url_patterns=(r"api\.x\.ai",),
    ),
    ProviderSpec(
        canonical_name="anthropic",
        aliases=("anthropic",),
        builder=lambda model, base_url=None, **kwargs: AnthropicClient(model, base_url, **kwargs),
        base_url_patterns=(r"api\.anthropic\.com", r"api\.minimaxi\.com/anthropic"),
    ),
    ProviderSpec(
        canonical_name="google",
        aliases=("google",),
        builder=lambda model, base_url=None, **kwargs: GoogleClient(model, base_url, **kwargs),
        base_url_patterns=(r"generativelanguage\.googleapis\.com",),
    ),
)


def get_provider_spec(provider: str) -> ProviderSpec:
    """Resolve a provider or alias to its canonical registry entry."""
    provider_lower = provider.lower()
    for spec in _PROVIDER_SPECS:
        if provider_lower in spec.aliases:
            return spec
    raise ValueError(f"Unsupported LLM provider: {provider}")


def get_supported_providers() -> tuple[str, ...]:
    """Return canonical provider names exposed by the registry."""
    return tuple(spec.canonical_name for spec in _PROVIDER_SPECS)


def create_llm_client(
    provider: str,
    model: str,
    base_url: Optional[str] = None,
    **kwargs,
) -> BaseLLMClient:
    """Create an LLM client for the specified provider.

    Args:
        provider: LLM provider name
        model: Model name/identifier
        base_url: Optional base URL for API endpoint
        **kwargs: Additional provider-specific arguments

    Returns:
        Configured BaseLLMClient instance

    Raises:
        ValueError: If provider is not supported
    """
    provider_lower = provider.lower()
    provider_spec = get_provider_spec(provider_lower)
    return provider_spec.builder(model, base_url, **kwargs)


def validate_provider_base_url(provider: str, base_url: str) -> Optional[dict]:
    """Validate provider × base_url compatibility.

    Args:
        provider: LLM provider name (original, not canonical)
        base_url: API endpoint URL

    Returns:
        None if valid, or dict with mismatch details if invalid:
        {
            "provider": str,
            "backend_url": str,
            "expected_patterns": tuple[str, ...]
        }
    """
    if not provider or not base_url:
        return None

    provider_lower = provider.lower()
    base_url_lower = base_url.lower()

    try:
        spec = get_provider_spec(provider_lower)
    except ValueError:
        # Unknown provider - no validation rules
        return None

    if spec.base_url_patterns is None:
        # No validation rules defined for this provider
        return None

    # Compile and test patterns
    for pattern_str in spec.base_url_patterns:
        pattern = re.compile(pattern_str)
        if pattern.search(base_url_lower):
            return None  # Match found

    # No pattern matched - return mismatch details
    return {
        "provider": provider_lower,
        "backend_url": base_url,
        "expected_patterns": spec.base_url_patterns,
    }
