from .base_client import BaseLLMClient


_SUPPORTED_PROVIDERS = ("anthropic", "openai")


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

    Args:
        provider: LLM provider — "anthropic" or "openai"
        model: Model name/identifier
        base_url: Optional custom API base URL
        **kwargs: Additional provider-specific arguments

    Returns:
        Configured BaseLLMClient instance

    Raises:
        ValueError: If provider is not supported
    """
    key = provider.lower()

    if key == "anthropic":
        from .anthropic_client import AnthropicClient
        return AnthropicClient(model, base_url, **kwargs)

    if key == "openai":
        from .openai_client import OpenAIClient
        return OpenAIClient(model, base_url, **kwargs)

    raise ValueError(
        f"Unsupported LLM provider: {provider!r}. "
        f"Supported: {', '.join(_SUPPORTED_PROVIDERS)}"
    )

