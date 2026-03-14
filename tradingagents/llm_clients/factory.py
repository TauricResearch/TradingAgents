from typing import Optional

from .base_client import BaseLLMClient


def create_llm_client(
    provider: str,
    model: str,
    base_url: Optional[str] = None,
    **kwargs,
) -> BaseLLMClient:
    """Create an LLM client for the specified provider.

    Args:
        provider: LLM provider (openai, codex_oauth, anthropic, google, xai, ollama, openrouter)
        model: Model name/identifier
        base_url: Optional base URL for API endpoint
        **kwargs: Additional provider-specific arguments

    Returns:
        Configured BaseLLMClient instance

    Raises:
        ValueError: If provider is not supported
    """
    provider_lower = provider.lower()

    if provider_lower in ("openai", "ollama", "openrouter"):
        try:
            from .openai_client import OpenAIClient
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "Missing dependency for OpenAI-compatible providers. "
                "Install `langchain-openai`."
            ) from exc

        return OpenAIClient(model, base_url, provider=provider_lower, **kwargs)

    if provider_lower == "codex_oauth":
        try:
            from .codex_oauth_client import CodexOAuthClient
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "Missing dependency for codex_oauth provider. "
                "Install `langchain-codex-oauth`."
            ) from exc

        return CodexOAuthClient(model, base_url, **kwargs)

    if provider_lower == "xai":
        try:
            from .openai_client import OpenAIClient
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "Missing dependency for xAI provider. Install `langchain-openai`."
            ) from exc

        return OpenAIClient(model, base_url, provider="xai", **kwargs)

    if provider_lower == "anthropic":
        try:
            from .anthropic_client import AnthropicClient
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "Missing dependency for Anthropic provider. "
                "Install `langchain-anthropic`."
            ) from exc

        return AnthropicClient(model, base_url, **kwargs)

    if provider_lower == "google":
        try:
            from .google_client import GoogleClient
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "Missing dependency for Google provider. "
                "Install `langchain-google-genai`."
            ) from exc

        return GoogleClient(model, base_url, **kwargs)

    raise ValueError(f"Unsupported LLM provider: {provider}")
