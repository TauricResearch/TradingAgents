import os
import re
from typing import Any

from langchain_anthropic import ChatAnthropic

from .api_key_env import is_anthropic_setup_token
from .base_client import BaseLLMClient, normalize_content
from .retry import call_with_rate_limit_retry
from .validators import validate_model

_PASSTHROUGH_KWARGS = (
    "timeout", "max_retries", "api_key", "max_tokens", "temperature",
    "callbacks", "http_client", "http_async_client", "effort",
    "default_headers", "rate_limiter",
)

# Anthropic's extended-thinking ``effort`` parameter is accepted by Opus 4.5+
# and Sonnet 4.6+ only. Sonnet 4.5 and any Haiku version 400 with
# ``"This model does not support the effort parameter"`` (#831). The per-family
# minimum version below is forward-compatible: future ``claude-{opus,sonnet}-X-Y``
# releases inherit support automatically, while Sonnet 4.5 and Haiku stay excluded.
_EFFORT_EXACT = {
    "claude-mythos-preview",  # non-standard preview name; effort-capable
}
_EFFORT_MODEL = re.compile(r"^claude-(opus|sonnet)-(\d+)-(\d+)$")
_EFFORT_MIN_VERSION = {"opus": (4, 5), "sonnet": (4, 6)}


def _supports_effort(model: str) -> bool:
    """Whether Anthropic accepts the ``effort`` parameter for this model."""
    model_lc = model.lower()
    if model_lc in _EFFORT_EXACT:
        return True
    match = _EFFORT_MODEL.match(model_lc)
    if not match:
        return False
    family, major, minor = match.group(1), int(match.group(2)), int(match.group(3))
    return (major, minor) >= _EFFORT_MIN_VERSION[family]


# Block types that may carry ``cache_control`` per the Anthropic prompt-caching
# docs. thinking/redacted_thinking blocks reject the field, so the marker is
# placed on the last *eligible* block, not blindly on the last block.
_CACHE_ELIGIBLE_BLOCK_TYPES = frozenset(
    {"text", "image", "tool_use", "tool_result", "document"}
)


def _cache_disabled() -> bool:
    # Read at call time (same convention as the retry.py env knobs) so batch
    # scripts can flip it without re-importing.
    return os.environ.get("TRADINGAGENTS_ANTHROPIC_CACHE", "1").strip().lower() in (
        "0", "false", "no", "off",
    )


def _mark_last_eligible_block(blocks: list) -> None:
    for block in reversed(blocks):
        if isinstance(block, dict) and block.get("type") in _CACHE_ELIGIBLE_BLOCK_TYPES:
            block.setdefault("cache_control", {"type": "ephemeral"})
            return


def _as_block_list(content):
    """String content as a one-text-block list; lists pass through unchanged."""
    if isinstance(content, str) and content:
        return [{"type": "text", "text": content}]
    return content


def _inject_cache_control(payload: dict) -> None:
    """Add prompt-cache breakpoints to a finished Messages API payload.

    Two of the four allowed breakpoints are used:

    * the last system block — tools and system render before messages, so this
      caches the whole static prefix (analyst instructions, debate-round
      report blobs) that is resent verbatim on every call;
    * the last eligible block of the final message — a sliding breakpoint, so
      growing message lists (analyst tool loops, multi-turn debates) hit the
      cache incrementally via Anthropic's previous-breakpoint lookback.

    ``setdefault`` keeps the injection idempotent and never overrides a
    marker a caller placed deliberately. Payloads below the model's minimum
    cacheable size are marked too — the API just skips caching them.
    """
    system = _as_block_list(payload.get("system"))
    if isinstance(system, list) and system:
        payload["system"] = system
        _mark_last_eligible_block(system)

    messages = payload.get("messages") or []
    if messages:
        last = messages[-1]
        content = _as_block_list(last.get("content"))
        if isinstance(content, list) and content:
            last["content"] = content
            _mark_last_eligible_block(content)


class NormalizedChatAnthropic(ChatAnthropic):
    """ChatAnthropic with normalized content output.

    Claude models with extended thinking or tool use return content as a
    list of typed blocks. This normalizes to string for consistent
    downstream handling.

    ``invoke`` is also the single funnel for every chat call in the graph
    (plain, tool-bound, and structured-output runnables all delegate here),
    so the long-horizon rate-limit retry wraps it rather than each agent.

    ``_get_request_payload`` is likewise the single funnel for the outgoing
    request body (sync/async, generate and stream alike), so prompt-cache
    breakpoints are injected there — agents stay provider-neutral. The
    override-the-payload pattern matches DeepSeekChatOpenAI /
    MinimaxChatOpenAI in openai_client.py. Disable with
    ``TRADINGAGENTS_ANTHROPIC_CACHE=0`` if a langchain-anthropic upgrade
    ever changes the payload contract.
    """

    def invoke(self, input, config=None, **kwargs):
        parent_invoke = super().invoke
        return normalize_content(
            call_with_rate_limit_retry(
                lambda: parent_invoke(input, config, **kwargs),
                description=self.model,
            )
        )

    def _get_request_payload(self, input_, *, stop=None, **kwargs):
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        if not _cache_disabled():
            _inject_cache_control(payload)
        return payload


class AnthropicClient(BaseLLMClient):
    """Client for Anthropic Claude models."""

    def __init__(self, model: str, base_url: str | None = None, **kwargs):
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
