import logging

from .base_client import BaseLLMClient

logger = logging.getLogger(__name__)


def create_llm_client(
    provider: str,
    model: str,
    base_url: str | None = None,
    **kwargs,
) -> BaseLLMClient:
    """Create an LLM client for the specified provider.

    Provider modules are imported lazily so that simply importing this
    factory (e.g. during test collection) does not pull in heavy LLM SDKs
    or fail when their API keys are absent.

    To enable provider fallback, set the ``fallback_provider`` kwarg::

        create_llm_client(
            provider="openai", model="gpt-4o",
            fallback_provider="puter", fallback_model="gpt-4o-mini",
            ...
        )

    Args:
        provider: LLM provider name
        model: Model name/identifier
        base_url: Optional base URL for API endpoint
        **kwargs: Additional provider-specific arguments. If
            ``fallback_provider`` is set, a ``FallbackLLMClient`` is returned
            that tries the primary provider first and the fallback on failure.

    Returns:
        Configured BaseLLMClient instance (or FallbackLLMClient when
        a fallback provider is configured).

    Raises:
        ValueError: If provider is not supported
    """
    fallback_provider = kwargs.pop("fallback_provider", None)
    fallback_model = kwargs.pop("fallback_model", None)
    fallback_base_url = kwargs.pop("fallback_base_url", None)

    primary = _create_single_client(provider, model, base_url, **kwargs)

    if fallback_provider:
        from .fallback import FallbackLLMClient

        secondary = _create_single_client(
            fallback_provider,
            fallback_model or model,
            fallback_base_url or base_url,
            **kwargs,
        )
        logger.info(
            "LLM fallback enabled: primary=%s/%s, fallback=%s/%s",
            provider, model, fallback_provider, fallback_model or model,
        )
        return FallbackLLMClient(primary, secondary)

    return primary


def _create_single_client(
    provider: str,
    model: str,
    base_url: str | None = None,
    **kwargs,
) -> BaseLLMClient:
    """Create a single (non-fallback) LLM client."""
    provider_lower = provider.lower()

    # Native (non-OpenAI) APIs are matched first so their string check doesn't
    # import the OpenAI client. Everything else is OpenAI-compatible and routes
    # through the provider registry (single source of truth).
    if provider_lower == "anthropic":
        from .anthropic_client import AnthropicClient
        return AnthropicClient(model, base_url, **kwargs)

    if provider_lower == "google":
        from .google_client import GoogleClient
        return GoogleClient(model, base_url, **kwargs)

    if provider_lower == "azure":
        from .azure_client import AzureOpenAIClient
        return AzureOpenAIClient(model, base_url, **kwargs)

    if provider_lower == "bedrock":
        from .bedrock_client import BedrockClient
        return BedrockClient(model, base_url, **kwargs)

    from .openai_client import OpenAIClient, is_openai_compatible
    if is_openai_compatible(provider_lower):
        return OpenAIClient(model, base_url, provider=provider_lower, **kwargs)

    raise ValueError(f"Unsupported LLM provider: {provider}")
