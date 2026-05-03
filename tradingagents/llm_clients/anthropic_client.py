import os
from typing import Any, Optional

from langchain_anthropic import ChatAnthropic

from .base_client import BaseLLMClient, normalize_content
from .validators import validate_model

_PASSTHROUGH_KWARGS = (
    "timeout", "max_retries", "api_key", "max_tokens",
    "callbacks", "http_client", "http_async_client", "effort",
)

_PROVIDER_CONFIG = {
    "anthropic": ("https://api.anthropic.com/", ("ANTHROPIC_API_KEY",)),
    "mimo": ("https://token-plan-sgp.xiaomimimo.com/anthropic", ("MIMO_API_KEY",)),
}

_BASE_URL_ENV = {
    "anthropic": ("ANTHROPIC_BASE_URL",),
    "mimo": ("MIMO_BASE_URL",),
}


def _first_env_value(names: tuple[str, ...]) -> str | None:
    return next((os.environ.get(name) for name in names if os.environ.get(name)), None)


class NormalizedChatAnthropic(ChatAnthropic):
    """ChatAnthropic with normalized content output.

    Claude models with extended thinking or tool use return content as a
    list of typed blocks. This normalizes to string for consistent
    downstream handling.
    """

    def invoke(self, input, config=None, **kwargs):
        return normalize_content(super().invoke(input, config, **kwargs))


class AnthropicClient(BaseLLMClient):
    """Client for Anthropic-compatible chat models."""

    def __init__(
        self,
        model: str,
        base_url: Optional[str] = None,
        provider: str = "anthropic",
        **kwargs,
    ):
        super().__init__(model, base_url, **kwargs)
        self.provider = provider.lower()

    def get_llm(self) -> Any:
        """Return configured ChatAnthropic instance."""
        self.warn_if_unknown_model()
        llm_kwargs = {"model": self.model}

        default_base_url, api_key_envs = _PROVIDER_CONFIG.get(self.provider, (None, ()))
        base_url = self.base_url or _first_env_value(_BASE_URL_ENV.get(self.provider, ())) or default_base_url
        if base_url:
            llm_kwargs["base_url"] = base_url

        api_key = _first_env_value(api_key_envs)
        if api_key:
            llm_kwargs["api_key"] = api_key

        for key in _PASSTHROUGH_KWARGS:
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        return NormalizedChatAnthropic(**llm_kwargs)

    def validate_model(self) -> bool:
        """Validate model for the Anthropic-compatible provider."""
        return validate_model(self.provider, self.model)
