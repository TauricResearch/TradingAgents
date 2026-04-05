from .base_client import BaseLLMClient
from .anthropic_client import AnthropicClient


def create_llm_client(
    provider: str,
    model: str,
    base_url: str | None = None,
    **kwargs,
) -> BaseLLMClient:
    """Create an LLM client for the specified provider.

    Args:
        provider: LLM provider — only "anthropic" is supported
        model: Model name/identifier
        base_url: Unused; kept for call-site compatibility
        **kwargs: Additional provider-specific arguments
            - api_key: Anthropic API key
            - timeout: Request timeout in seconds
            - max_retries: Maximum retry attempts
            - max_tokens: Maximum tokens in the response
            - callbacks: LangChain callbacks
            - effort: Claude effort level ("high", "medium", "low")

    Returns:
        Configured AnthropicClient instance

    Raises:
        ValueError: If provider is not "anthropic"
    """
    if provider.lower() == "anthropic":
        return AnthropicClient(model, base_url, **kwargs)

    raise ValueError(f"Unsupported LLM provider: {provider!r}. Only 'anthropic' is supported.")
