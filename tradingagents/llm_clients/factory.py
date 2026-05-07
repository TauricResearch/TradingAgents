import logging
import warnings
from typing import Optional

from .base_client import BaseLLMClient

logger = logging.getLogger(__name__)

# Providers that use the OpenAI-compatible chat completions API
_OPENAI_COMPATIBLE = (
    "openai", "xai", "deepseek", "qwen", "glm", "ollama", "openrouter",
)


def create_llm_client(
    provider: str,
    model: str,
    base_url: Optional[str] = None,
    **kwargs,
) -> BaseLLMClient:
    """Create an LLM client for the specified provider.

    Provider modules are imported lazily so that simply importing this
    factory (e.g. during test collection) does not pull in heavy LLM SDKs
    or fail when their API keys are absent.

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

    # Validate the model name against the known catalog early so typos or
    # stale default config values surface immediately rather than at first LLM call.
    from .validators import validate_model
    if not validate_model(provider_lower, model):
        warnings.warn(
            f"Model '{model}' is not in the known catalog for provider '{provider}'. "
            "The API call may fail. Check your config or model name.",
            UserWarning,
            stacklevel=2,
        )
        logger.warning("Unknown model '%s' for provider '%s'", model, provider)

    if provider_lower in _OPENAI_COMPATIBLE:
        from .openai_client import OpenAIClient
        return OpenAIClient(model, base_url, provider=provider_lower, **kwargs)

    if provider_lower == "anthropic":
        from .anthropic_client import AnthropicClient
        return AnthropicClient(model, base_url, **kwargs)

    if provider_lower == "google":
        from .google_client import GoogleClient
        return GoogleClient(model, base_url, **kwargs)

    if provider_lower == "azure":
        from .azure_client import AzureOpenAIClient
        return AzureOpenAIClient(model, base_url, **kwargs)

    raise ValueError(f"Unsupported LLM provider: {provider}")
