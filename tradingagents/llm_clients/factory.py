from .base_client import BaseLLMClient
from .anthropic_client import AnthropicClient




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
        provider: LLM provider — only "anthropic" is supported

        model: Model name/identifier
        base_url: Unused; kept for call-site compatibility
        **kwargs: Additional provider-specific arguments


    Returns:
        Configured AnthropicClient instance

    Raises:
        ValueError: If provider is not "anthropic"
    """
    if provider.lower() == "anthropic":
        return AnthropicClient(model, base_url, **kwargs)

    raise ValueError(f"Unsupported LLM provider: {provider!r}. Only 'anthropic' is supported.")

