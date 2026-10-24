import re
from typing import Any

from langchain_anthropic import ChatAnthropic

from .base_client import BaseLLMClient, normalize_content
from .validators import validate_model

_PASSTHROUGH_KWARGS = (
    "timeout", "max_retries", "api_key", "max_tokens", "temperature",
    "callbacks", "http_client", "http_async_client", "effort",
)

# Anthropic's extended-thinking ``effort`` parameter is accepted by Opus 4.5+,
# Sonnet 4.6+, and the Claude 5 family (Sonnet 5, Opus 5.5, Fable 5). Sonnet 4.5 and any
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


# langchain-anthropic's default structured-output method is forced tool calling,
# which Claude 5.5-era models (Opus 5.5, Sonnet 5.5, Fable 5.1) reject outright
# and every thinking-enabled model treats as optional. The structured call then
# returns nothing and the agent pays for a free-text retry. Models with native
# structured outputs (``output_config.format``) use that instead: the Claude 5
# family, plus Opus 4.1 / 4.5 / 4.8 and Haiku 4.5. Opus 4.6 / 4.7 and Sonnet
# 4.5 / 4.6 are not on Anthropic's supported list, so they keep tool calling.
_JSON_SCHEMA_4X = {"opus-4-1", "opus-4-5", "opus-4-8", "haiku-4-5"}
_CLAUDE_MODEL = re.compile(r"^claude-(opus|sonnet|haiku|fable|mythos)-(\d+)(?:-(\d+))?(?:-\d{8})?$")


def _supports_json_schema(model: str) -> bool:
    """Whether the model supports Anthropic's native structured outputs."""
    match = _CLAUDE_MODEL.match(model.lower())
    if not match:
        return False
    family, major, minor = match.group(1), int(match.group(2)), match.group(3) or "0"
    if major >= 5:
        return True
    return f"{family}-{major}-{minor}" in _JSON_SCHEMA_4X


class NormalizedChatAnthropic(ChatAnthropic):
    """ChatAnthropic with normalized content output and model-aware structured output.

    Claude models with extended thinking or tool use return content as a
    list of typed blocks. This normalizes to string for consistent
    downstream handling.
    """

    def invoke(self, input, config=None, **kwargs):
        return normalize_content(super().invoke(input, config, **kwargs))

    def with_structured_output(self, schema, *, method=None, **kwargs):
        if method is None:
            method = "json_schema" if _supports_json_schema(self.model) else "function_calling"
        return super().with_structured_output(schema, method=method, **kwargs)


class AnthropicClient(BaseLLMClient):
    """Client for Anthropic Claude models."""

    def __init__(self, model: str, base_url: str | None = None, **kwargs):
        super().__init__(model, base_url, **kwargs)

    def get_llm(self) -> Any:
        """Return configured ChatAnthropic instance."""
        self.warn_if_unknown_model()
        llm_kwargs = {"model": self.model}

        if self.base_url:
            llm_kwargs["base_url"] = self.base_url

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
