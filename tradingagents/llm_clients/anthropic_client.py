import os
import re
from typing import Any

from langchain_anthropic import ChatAnthropic

from .base_client import BaseLLMClient, normalize_content
from .validators import validate_model

_PASSTHROUGH_KWARGS = (
    "timeout", "max_retries", "api_key", "max_tokens", "temperature",
    "callbacks", "http_client", "http_async_client", "effort",
)

# Provider-specific default base URL and API-key env vars. MiMo is an
# Anthropic-protocol provider (Xiaomi) with its own endpoint and key.
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

# Anthropic's extended-thinking ``effort`` parameter is accepted by Opus 4.5+,
# Sonnet 4.6+, and the Claude 5 family (Sonnet 5, Fable 5). Sonnet 4.5 and any
# Haiku version 400 with ``"This model does not support the effort parameter"``
# (#831). Versions may be dotted (``opus-4-8``) or single-number (``sonnet-5``,
# ``fable-5``); the per-family minimum below is forward-compatible.
_EFFORT_EXACT = {
    "claude-mythos-preview",  # non-standard preview name; effort-capable
    "claude-mythos-5",        # Fable 5 twin (Project Glasswing); effort-capable
}
_EFFORT_MODEL = re.compile(r"^claude-(opus|sonnet|fable)-(\d+)(?:-(\d+))?$")
_EFFORT_MIN_VERSION = {"opus": (4, 5), "sonnet": (4, 6), "fable": (5, 0)}


def _supports_effort(model: str) -> bool:
    """Whether Anthropic accepts the ``effort`` parameter for this model."""
    model_lc = model.lower()
    if model_lc in _EFFORT_EXACT:
        return True
    match = _EFFORT_MODEL.match(model_lc)
    if not match:
        return False
    family = match.group(1)
    major = int(match.group(2))
    minor = int(match.group(3)) if match.group(3) else 0
    return (major, minor) >= _EFFORT_MIN_VERSION[family]


class NormalizedChatAnthropic(ChatAnthropic):
    """ChatAnthropic with normalized content output.

    Claude models with extended thinking or tool use return content as a
    list of typed blocks. This normalizes to string for consistent
    downstream handling.
    """

    def invoke(self, input, config=None, **kwargs):
        return normalize_content(super().invoke(input, config, **kwargs))


class AnthropicClient(BaseLLMClient):
    """Client for Anthropic Claude models."""

    def __init__(self, model: str, base_url: str | None = None, provider: str = "anthropic", **kwargs):
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
            if key not in self.kwargs:
                continue
            if key == "effort" and not _supports_effort(self.model):
                continue
            llm_kwargs[key] = self.kwargs[key]

        return NormalizedChatAnthropic(**llm_kwargs)

    def validate_model(self) -> bool:
        """Validate model for Anthropic."""
        return validate_model("anthropic", self.model)
