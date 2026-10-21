"""Declarative per-model capability table for OpenAI-compatible providers.

This is the single place that knows which model IDs reject which API
parameters or require which structured-output method. The LLM client
subclasses consult ``get_capabilities(model_name)`` instead of hardcoding
model-name ``if`` ladders, so adding a new model (or a new provider quirk)
means editing this table — not the client code.

Pattern adapted from the per-model ``compat:`` flags DeepSeek themselves
publish in their integration guides (e.g. the Oh My Pi config schema
documents ``supportsToolChoice``, ``requiresReasoningContentForToolCalls``
as declarative per-model fields).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

StructuredMethod = Literal[
    "function_calling",  # uses tools; respects supports_tool_choice
    "json_mode",         # uses response_format={"type":"json_object"}
    "json_schema",       # uses response_format={"type":"json_schema",...}
    "none",              # no structured output available; caller falls back to free-text
]
ThinkingMode = Literal["always_on", "adaptive", "disabled"]


@dataclass(frozen=True)
class ModelCapabilities:
    """What an OpenAI-compatible model accepts at the API level."""

    supports_tool_choice: bool
    supports_json_mode: bool
    supports_json_schema: bool
    preferred_structured_method: StructuredMethod
    # DeepSeek thinking-mode models 400 if reasoning_content from prior
    # assistant turns is not echoed back on the next request.
    requires_reasoning_content_roundtrip: bool = False
    # MiniMax M2.x reasoning models need ``reasoning_split=True`` so the
    # <think> block lands in ``reasoning_details`` instead of polluting
    # ``content``. The flag is rejected by non-reasoning MiniMax models
    # (Coding Plan, MiniMax-Text-01, etc.), so we only set it where the
    # model actually consumes it. (#826)
    requires_reasoning_split: bool = False
    # Supported MiniMax thinking controls. An empty tuple means the provider
    # does not publish a model-specific thinking mode through this layer.
    thinking_modes: tuple[ThinkingMode, ...] = ()
    # MiniMax-M3.1-Flash accepts OpenAI's reasoning_effort parameter; M3 ignores
    # it and M2.x exposes only its always-on mode.
    supports_reasoning_effort: bool = False


# DeepSeek's thinking models accept the ``tools`` array but reject the
# ``tool_choice`` parameter (official Oh My Pi integration guide and the
# 400 response in issue #678). Their official tool-calling examples
# (api-docs.deepseek.com/guides/tool_calls) pass ``tools=[...]`` without
# ``tool_choice`` — we mirror that pattern by setting supports_tool_choice
# to False and letting the client suppress the kwarg.
_DEEPSEEK_THINKING = ModelCapabilities(
    supports_tool_choice=False,
    supports_json_mode=True,
    supports_json_schema=False,
    preferred_structured_method="function_calling",
    requires_reasoning_content_roundtrip=True,
)

_DEEPSEEK_CHAT = ModelCapabilities(
    supports_tool_choice=True,
    supports_json_mode=True,
    supports_json_schema=False,
    preferred_structured_method="function_calling",
)

# MiniMax M2.x reasoning models accept the tools array, but their
# tool_choice parameter is restricted to the enum {"none", "auto"}
# (platform.minimax.io/docs/api-reference/text-post). Langchain's
# function_calling path sends tool_choice as a function-spec dict, which
# MiniMax 400s — same shape as the DeepSeek bug. supports_tool_choice=False
# makes the dispatch in NormalizedChatOpenAI suppress the kwarg; the schema
# still ships as a tool. json_mode response_format is only for
# MiniMax-Text-01, not M2.x.
_MINIMAX_M2 = ModelCapabilities(
    supports_tool_choice=False,
    supports_json_mode=False,
    supports_json_schema=False,
    preferred_structured_method="function_calling",
    requires_reasoning_split=True,
    thinking_modes=("always_on",),
)

# M3 supports per-request adaptive or disabled thinking while retaining the
# existing MiniMax tool-calling and reasoning-split behavior.
_MINIMAX_M3 = ModelCapabilities(
    supports_tool_choice=False,
    supports_json_mode=False,
    supports_json_schema=False,
    preferred_structured_method="function_calling",
    requires_reasoning_split=True,
    thinking_modes=("adaptive", "disabled"),
)

# Flash is adaptive-only. It has its own exact row so it never inherits M2's
# reasoning_split requirement or M3's disabled-thinking allowance.
_MINIMAX_FLASH = ModelCapabilities(
    supports_tool_choice=False,
    supports_json_mode=False,
    supports_json_schema=False,
    preferred_structured_method="function_calling",
    thinking_modes=("adaptive",),
    supports_reasoning_effort=True,
)

_DEFAULT = ModelCapabilities(
    supports_tool_choice=True,
    supports_json_mode=True,
    supports_json_schema=True,
    preferred_structured_method="function_calling",
)


# Exact-ID matches take precedence over pattern matches.
_BY_ID: dict[str, ModelCapabilities] = {
    "deepseek-chat": _DEEPSEEK_CHAT,
    "deepseek-reasoner": _DEEPSEEK_THINKING,
    "deepseek-flash": _DEEPSEEK_THINKING,
    "deepseek-v4-flash": _DEEPSEEK_THINKING,
    "deepseek-v4-pro": _DEEPSEEK_THINKING,
    # MiniMax — full official model lineup per
    # platform.minimax.io/docs/api-reference/text-openai-api
    "MiniMax-M3.1-Flash": _MINIMAX_FLASH,
    "MiniMax-M3": _MINIMAX_M3,
    "MiniMax-M2.7": _MINIMAX_M2,
    "MiniMax-M2.7-highspeed": _MINIMAX_M2,
    "MiniMax-M2.5": _MINIMAX_M2,
    "MiniMax-M2.5-highspeed": _MINIMAX_M2,
    "MiniMax-M2.1": _MINIMAX_M2,
    "MiniMax-M2.1-highspeed": _MINIMAX_M2,
    "MiniMax-M2": _MINIMAX_M2,
}

# Forward-compat patterns. New ``deepseek-v5-*`` / ``deepseek-reasoner-*``
# / ``deepseek-flash-*`` or MiniMax M2.x variants inherit the established
# thinking-mode quirks. Exact M3/Flash IDs above keep their newer controls.
_BY_PATTERN: list[tuple[re.Pattern[str], ModelCapabilities]] = [
    (re.compile(r"^deepseek-v\d"), _DEEPSEEK_THINKING),
    (re.compile(r"^deepseek-reasoner"), _DEEPSEEK_THINKING),
    (re.compile(r"^deepseek-flash"), _DEEPSEEK_THINKING),
    (re.compile(r"^MiniMax-M2(?:\D|$)"), _MINIMAX_M2),
]


def get_capabilities(model_name: str) -> ModelCapabilities:
    """Resolve capabilities by exact ID, then pattern, then default."""
    # OpenRouter namespaces official DeepSeek models as ``deepseek/<id>``, so
    # strip that prefix to reuse the same quirks as the native provider — e.g.
    # ``deepseek/deepseek-v4-flash`` must suppress tool_choice like
    # ``deepseek-v4-flash`` does, not fall through to _DEFAULT (#1199). Only the
    # official namespace is stripped; third-party finetunes on other publishers
    # (e.g. ``tngtech/deepseek-...``) keep _DEFAULT, since their quirks are unknown.
    if model_name.startswith("deepseek/"):
        model_name = model_name.removeprefix("deepseek/")

    if model_name in _BY_ID:
        return _BY_ID[model_name]
    for pattern, caps in _BY_PATTERN:
        if pattern.match(model_name):
            return caps
    return _DEFAULT
