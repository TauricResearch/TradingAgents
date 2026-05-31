import os
from typing import Optional

from .base_client import BaseLLMClient
from .api_key_env import get_api_key_env


TENCENT_ANTHROPIC_BASE_URL = "https://api.lkeap.cloud.tencent.com/plan/anthropic"

# Providers that use the OpenAI-compatible chat completions API
_OPENAI_COMPATIBLE = (
    "openai", "xai", "deepseek",
    "qwen", "qwen-cn",
    "glm", "glm-cn",
    "minimax", "minimax-cn",
    "ollama", "openrouter",
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

    if provider_lower in _OPENAI_COMPATIBLE:
        from .openai_client import OpenAIClient
        return OpenAIClient(model, base_url, provider=provider_lower, **kwargs)

    if provider_lower in ("anthropic", "tencent"):
        from .anthropic_client import AnthropicClient
        if provider_lower == "tencent":
            base_url = base_url or TENCENT_ANTHROPIC_BASE_URL
            api_key_env = get_api_key_env(provider_lower)
            if not kwargs.get("api_key") and api_key_env:
                api_key = os.environ.get(api_key_env)
                if api_key:
                    kwargs["api_key"] = api_key
                else:
                    raise ValueError(
                        f"API key for provider '{provider_lower}' is not set. "
                        f"Please set the {api_key_env} environment variable "
                        f"(e.g. add {api_key_env}=your_key to your .env file)."
                    )
        return AnthropicClient(model, base_url, provider=provider_lower, **kwargs)

    if provider_lower == "google":
        from .google_client import GoogleClient
        return GoogleClient(model, base_url, **kwargs)

    if provider_lower == "azure":
        from .azure_client import AzureOpenAIClient
        return AzureOpenAIClient(model, base_url, **kwargs)

    raise ValueError(f"Unsupported LLM provider: {provider}")
