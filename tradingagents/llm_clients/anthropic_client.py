import copy
import re
from typing import Any

from langchain_anthropic import ChatAnthropic

from .base_client import BaseLLMClient, normalize_content
from .validators import validate_model

_PASSTHROUGH_KWARGS = (
    "timeout", "max_retries", "api_key", "max_tokens", "temperature",
    "callbacks", "http_client", "http_async_client", "effort",
)

_CACHE_CONTROL_EPHEMERAL = {"type": "ephemeral"}

# Conservative output-token floors for supported Claude 5 models when effort is
# enabled but the caller did not provide an explicit max_tokens cap.
_EFFORT_MAX_TOKENS = {
    "opus": {"low": 8192, "medium": 12288, "high": 16384},
    "sonnet": {"low": 8192, "medium": 12288, "high": 16384},
    "fable": {"low": 12288, "medium": 16384, "high": 24576},
}

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


def _resolve_anthropic_max_tokens(
    model: str,
    effort: str | None,
    max_tokens: int | None,
) -> int | None:
    """Pick a safer max_tokens floor when effort is enabled.

    Anthropic's reasoning-heavy Claude 5 calls can spend a meaningful part of
    the completion budget on internal thinking. If the caller did not set an
    explicit cap, allocate a family-aware floor instead of relying on the
    SDK's default.
    """
    if max_tokens is not None:
        return max_tokens

    if not effort or not _supports_effort(model):
        return None

    model_lc = model.lower()
    if "mythos" in model_lc:
        family = "fable"
    else:
        match = _EFFORT_MODEL.match(model_lc)
        if not match:
            return None
        family = match.group(1)

    effort_lc = effort.lower()
    return _EFFORT_MAX_TOKENS.get(family, {}).get(effort_lc)


def _add_cache_control(block: dict[str, Any]) -> dict[str, Any]:
    block.setdefault("cache_control", _CACHE_CONTROL_EPHEMERAL)
    return block


def _apply_prompt_caching(payload: dict[str, Any]) -> dict[str, Any]:
    """Mark static Anthropic prompt segments as cacheable."""
    cached_payload = copy.deepcopy(payload)

    system = cached_payload.get("system")
    if isinstance(system, str):
        cached_payload["system"] = [
            {
                "type": "text",
                "text": system,
                "cache_control": _CACHE_CONTROL_EPHEMERAL,
            }
        ]
    elif isinstance(system, list) and system:
        for index in range(len(system) - 1, -1, -1):
            block = system[index]
            if isinstance(block, dict):
                system[index] = _add_cache_control(block)
                break

    tools = cached_payload.get("tools")
    if isinstance(tools, list) and tools:
        for index in range(len(tools) - 1, -1, -1):
            tool = tools[index]
            if isinstance(tool, dict):
                tools[index] = _add_cache_control(tool)
                break

    return cached_payload


class NormalizedChatAnthropic(ChatAnthropic):
    """ChatAnthropic with normalized content output.

    Claude models with extended thinking or tool use return content as a
    list of typed blocks. This normalizes to string for consistent
    downstream handling.
    """

    def invoke(self, input, config=None, **kwargs):
        return normalize_content(super().invoke(input, config, **kwargs))

    def _get_request_payload(self, input_, *, stop=None, **kwargs):
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        return _apply_prompt_caching(payload)


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

        resolved_max_tokens = _resolve_anthropic_max_tokens(
            self.model,
            llm_kwargs.get("effort"),
            llm_kwargs.get("max_tokens"),
        )
        if resolved_max_tokens is not None:
            llm_kwargs["max_tokens"] = resolved_max_tokens

        return NormalizedChatAnthropic(**llm_kwargs)

    def validate_model(self) -> bool:
        """Validate model for Anthropic."""
        return validate_model("anthropic", self.model)
