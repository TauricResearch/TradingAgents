from dataclasses import dataclass
from typing import Callable, Optional

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
    """Provider registry entry for LLM client creation."""

    canonical_name: str
    aliases: tuple[str, ...]
    builder: Callable[..., BaseLLMClient]


_PROVIDER_SPECS: tuple[ProviderSpec, ...] = (
    ProviderSpec(
        canonical_name="openai",
        aliases=("openai", "ollama", "openrouter"),
        builder=lambda model, base_url=None, **kwargs: OpenAIClient(
            model,
            base_url,
            provider=kwargs.pop("provider", "openai"),
            **kwargs,
        ),
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
    ),
    ProviderSpec(
        canonical_name="anthropic",
        aliases=("anthropic",),
        builder=lambda model, base_url=None, **kwargs: AnthropicClient(model, base_url, **kwargs),
    ),
    ProviderSpec(
        canonical_name="google",
        aliases=("google",),
        builder=lambda model, base_url=None, **kwargs: GoogleClient(model, base_url, **kwargs),
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
    builder_kwargs = dict(kwargs)
    if provider_lower in ("openai", "ollama", "openrouter"):
        builder_kwargs["provider"] = provider_lower
    return provider_spec.builder(model, base_url, **builder_kwargs)
