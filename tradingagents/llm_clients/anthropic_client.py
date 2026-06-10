import os
import re
from typing import Any, Optional

from langchain_anthropic import ChatAnthropic

from .base_client import BaseLLMClient, normalize_content
from .api_key_env import is_anthropic_setup_token
from .retry import call_with_rate_limit_retry
from .validators import validate_model

_PASSTHROUGH_KWARGS = (
    "timeout", "max_retries", "api_key", "max_tokens", "temperature",
    "callbacks", "http_client", "http_async_client", "effort",
    "default_headers",
)

# Anthropic's extended-thinking ``effort`` parameter is accepted by Opus 4.5+
# and Sonnet 4.5+ only. Haiku (any version shipped to date) 400s with
# ``"This model does not support the effort parameter"`` (#831). Future
# ``claude-{opus,sonnet}-X-Y`` releases inherit effort support via the
# forward-compat pattern below; future Haiku stays excluded by default.
_EFFORT_EXACT = {
    "claude-mythos-preview",  # non-standard preview name; effort-capable
}
_EFFORT_PATTERN = re.compile(r"^claude-(opus|sonnet)-\d+-\d+$")


def _supports_effort(model: str) -> bool:
    """Whether Anthropic accepts the ``effort`` parameter for this model."""
    model_lc = model.lower()
    return model_lc in _EFFORT_EXACT or bool(_EFFORT_PATTERN.match(model_lc))


class NormalizedChatAnthropic(ChatAnthropic):
    """ChatAnthropic with normalized content output.

    Claude models with extended thinking or tool use return content as a
    list of typed blocks. This normalizes to string for consistent
    downstream handling.

    ``invoke`` is also the single funnel for every chat call in the graph
    (plain, tool-bound, and structured-output runnables all delegate here),
    so the long-horizon rate-limit retry wraps it rather than each agent.
    """

    def invoke(self, input, config=None, **kwargs):
        parent_invoke = super().invoke
        return normalize_content(
            call_with_rate_limit_retry(
                lambda: parent_invoke(input, config, **kwargs),
                description=self.model,
            )
        )


class AnthropicClient(BaseLLMClient):
    """Client for Anthropic Claude models."""

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        super().__init__(model, base_url, **kwargs)

    def get_llm(self) -> Any:
        """Return configured ChatAnthropic instance."""
        self.warn_if_unknown_model()
        api_key = self.kwargs.get("api_key") or os.environ.get("ANTHROPIC_API_KEY")
        llm_kwargs = {"model": self.model}

        if self.base_url:
            llm_kwargs["base_url"] = self.base_url

        using_setup_token = bool(api_key and is_anthropic_setup_token(api_key))
        if using_setup_token:
            headers = dict(self.kwargs.get("default_headers") or {})
            headers["Authorization"] = f"Bearer {api_key}"
            # ChatAnthropic requires an api_key string, while the Anthropic
            # SDK accepts Bearer auth when X-Api-Key is omitted or empty.
            llm_kwargs["api_key"] = ""
            llm_kwargs["default_headers"] = headers

        for key in _PASSTHROUGH_KWARGS:
            if key not in self.kwargs:
                continue
            if using_setup_token and key in ("api_key", "default_headers"):
                continue
            if key == "effort" and not _supports_effort(self.model):
                continue
            llm_kwargs[key] = self.kwargs[key]

        return NormalizedChatAnthropic(**llm_kwargs)

    def validate_model(self) -> bool:
        """Validate model for Anthropic."""
        return validate_model("anthropic", self.model)
