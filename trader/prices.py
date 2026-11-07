"""Official per-token prices of the models in the upstream model catalog.

The dashboard's model switch prices a model from this table, and the trader uses that price
to account LLM costs and set the monthly budget. Prices are USD per million tokens, input and
output, the unit of ``Settings.price_deep`` and ``Settings.price_quick``.

The table is maintained by hand. Every entry names the official page its numbers were read
from and the day they were read, so a stale price shows and can be rechecked at its source.
An entry records:

- the standard rate: not batch, not cached, not a priority or fast tier;
- for a model priced in tiers (by prompt length, by time of day), the lowest tier, named in
  the note;
- a promotional rate printed as the price itself, with its end date in the note; a
  limited-time discount shown on top of a list price is left out and mentioned in the note;
- for a price published only in CNY, a conversion at 7.2 CNY per USD, with the CNY price in
  the note.

A catalog model with no official price goes into UNPRICED with the reason, never a guessed
price. Keys are model ids exactly as the upstream catalog spells them. Providers with an
international and a China endpoint share ids (qwen and qwen-cn, glm and glm-cn, minimax and
minimax-cn); the table holds the international price and the note gives the China one.
Anthropic models the catalog has not caught up with are priced too, under their Claude API
aliases.

The module must stay importable on its own: it imports nothing from tradingagents.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Price:
    """A model's official per-token price, as read from the provider's pricing page."""

    input: float    # USD per million input tokens
    output: float   # USD per million output tokens
    source: str     # the official pricing page the numbers were read from
    as_of: str      # YYYY-MM-DD the page was read
    note: str = ""  # tier taken, currency conversion, anything a reader should know


_CNY_PER_USD = 7.2

_OPENAI = "https://platform.openai.com/docs/pricing"
_ANTHROPIC = "https://platform.claude.com/docs/en/about-claude/pricing"
_GOOGLE = "https://ai.google.dev/gemini-api/docs/pricing"
_XAI = "https://docs.x.ai/docs/models"
_DEEPSEEK = "https://api-docs.deepseek.com/quick_start/pricing/"
_QWEN = "https://www.alibabacloud.com/help/en/model-studio/model-pricing"
_ZAI = "https://docs.z.ai/guides/overview/pricing"
_BIGMODEL = "https://docs.bigmodel.cn/cn/guide/start/pricing"
_MINIMAX = "https://platform.minimax.io/docs/guides/pricing"

OFFICIAL: dict[str, Price] = {
    "gpt-6-astra": Price(
        10.0, 50.0, _OPENAI, "2026-11-07",
        "Short-context rate (up to 272K input tokens); longer prompts $20/$75.",
    ),
    "gpt-6-sol": Price(
        2.0, 10.0, _OPENAI, "2026-11-07",
        "Short-context rate (up to 272K input tokens); longer prompts $4/$15.",
    ),
    "gpt-6-luna": Price(
        0.1, 0.5, _OPENAI, "2026-11-07",
        "Short-context rate (up to 272K input tokens); longer prompts $0.20/$0.75.",
    ),
    "gpt-5.6-sol": Price(
        4.0, 20.0, _OPENAI, "2026-11-07",
        "Promotional rate, available until 2026-11-30; the page does not give the rate after "
        "it. Short-context rate (up to 272K input tokens); longer prompts $8/$30.",
    ),
    "gpt-5.6": Price(
        4.0, 20.0, "https://developers.openai.com/api/docs/models/gpt-5.6", "2026-11-07",
        "Alias that routes to gpt-5.6-sol, at its price: promotional until 2026-11-30, for "
        "prompts up to 272K input tokens (longer: $8/$30).",
    ),
    "gpt-5.6-terra": Price(
        2.0, 12.0, _OPENAI, "2026-11-07",
        "Short-context rate (up to 272K input tokens); longer prompts $4/$18.",
    ),
    "gpt-5.6-luna": Price(
        0.2, 1.2, _OPENAI, "2026-11-07",
        "Short-context rate (up to 272K input tokens); longer prompts $0.40/$1.80.",
    ),
    "gpt-5.5": Price(
        5.0, 30.0, _OPENAI, "2026-11-07",
        "Short-context rate (under 272K tokens); longer prompts $10/$45.",
    ),
    "gpt-5.4": Price(
        2.5, 15.0, _OPENAI, "2026-11-07",
        "Short-context rate (under 272K tokens); longer prompts $5/$22.50.",
    ),
    "gpt-5.4-mini": Price(0.75, 4.5, _OPENAI, "2026-11-07"),

    "claude-fable-5-1": Price(10.0, 50.0, _ANTHROPIC, "2026-11-07"),
    "claude-mythos-5-1": Price(
        10.0, 50.0, _ANTHROPIC, "2026-11-07",
        "Limited availability: organisations verified through Anthropic's programs only.",
    ),
    "claude-fable-5": Price(10.0, 50.0, _ANTHROPIC, "2026-11-07"),
    "claude-mythos-5": Price(
        10.0, 50.0, _ANTHROPIC, "2026-11-07",
        "Limited availability: organisations verified through Anthropic's programs only.",
    ),
    "claude-opus-5-5": Price(4.0, 20.0, _ANTHROPIC, "2026-11-07"),
    "claude-opus-5": Price(5.0, 25.0, _ANTHROPIC, "2026-11-07"),
    "claude-opus-4-8": Price(5.0, 25.0, _ANTHROPIC, "2026-11-07"),
    "claude-opus-4-7": Price(5.0, 25.0, _ANTHROPIC, "2026-11-07"),
    "claude-opus-4-6": Price(5.0, 25.0, _ANTHROPIC, "2026-11-07"),
    "claude-opus-4-5": Price(
        5.0, 25.0, _ANTHROPIC, "2026-11-07", "Alias of claude-opus-4-5-20251101.",
    ),
    "claude-sonnet-5-5": Price(2.0, 10.0, _ANTHROPIC, "2026-11-07"),
    "claude-sonnet-5": Price(
        2.0, 10.0, _ANTHROPIC, "2026-11-07",
        "The launch price became the standard price; the rise to $3/$15 planned for "
        "2026-09-01 was cancelled.",
    ),
    "claude-sonnet-4-6": Price(3.0, 15.0, _ANTHROPIC, "2026-11-07"),
    "claude-sonnet-4-5": Price(
        3.0, 15.0, _ANTHROPIC, "2026-11-07",
        "Alias of claude-sonnet-4-5-20250929; deprecated, retiring 2026-11-30.",
    ),
    "claude-haiku-5-5": Price(
        0.1, 0.5, _ANTHROPIC, "2026-11-07",
        "Prompts up to 100,000 tokens; longer prompts $0.50/$2.50.",
    ),
    "claude-haiku-4-5": Price(
        1.0, 5.0, _ANTHROPIC, "2026-11-07", "Alias of claude-haiku-4-5-20251001.",
    ),

    "gemini-3.8-flash": Price(
        0.75, 3.75, _GOOGLE, "2026-11-07",
        "Rate through 2026-12-31; $1.50/$7.50 from 2027-01-01.",
    ),
    "gemini-3.5-flash-lite": Price(0.3, 2.5, _GOOGLE, "2026-11-07"),
    "gemini-3.1-flash-lite": Price(
        0.25, 1.5, _GOOGLE, "2026-11-07",
        "Text, image and video input; audio input is $0.50.",
    ),
    "gemini-3.1-pro-preview": Price(
        2.0, 12.0, _GOOGLE, "2026-11-07",
        "Prompts up to 200K tokens; longer prompts $4/$18.",
    ),

    "grok-4.6": Price(
        2.0, 6.0, _XAI, "2026-11-07",
        "Prompts under 200K tokens; longer prompts $4/$12 for the whole request.",
    ),
    "grok-4.5": Price(
        2.0, 6.0, _XAI, "2026-11-07",
        "Prompts under 200K tokens; longer prompts $4/$12 for the whole request.",
    ),
    "grok-4.3": Price(
        1.25, 2.5, _XAI, "2026-11-07",
        "Prompts under 200K tokens; longer prompts $2.50/$5 for the whole request.",
    ),
    "grok-4.20-0309-reasoning": Price(
        1.25, 2.5, _XAI, "2026-11-07",
        "Prompts under 200K tokens; longer prompts $2.50/$5 for the whole request.",
    ),
    "grok-4.20-0309-non-reasoning": Price(
        1.25, 2.5, _XAI, "2026-11-07",
        "Prompts under 200K tokens; longer prompts $2.50/$5 for the whole request.",
    ),
    "grok-4.20-multi-agent-0309": Price(
        1.25, 2.5, _XAI, "2026-11-07",
        "Prompts under 200K tokens; longer prompts $2.50/$5 for the whole request.",
    ),
    "grok-build-0.1": Price(
        1.0, 2.0, _XAI, "2026-11-07",
        "Prompts under 200K tokens; longer prompts $2/$4 for the whole request.",
    ),

    "deepseek-flash": Price(
        0.15, 0.6, _DEEPSEEK, "2026-11-07",
        "Off-peak rate, the lower of two time-of-day tiers; peak (01:00-04:00 and 06:00-10:00 "
        "UTC on weekdays, Chinese public holidays excepted) is $0.30/$1.20. Served by "
        "DeepSeek-V4.1-Flash-1017.",
    ),
    "deepseek-v4-flash": Price(
        0.15, 0.6, _DEEPSEEK, "2026-11-07",
        "Legacy name, served by DeepSeek-V4.1-Flash-1017 at the deepseek-flash price. Off-peak "
        "rate; peak is $0.30/$1.20.",
    ),
    "deepseek-v4-pro": Price(
        0.66, 1.98, _DEEPSEEK, "2026-11-07",
        "Off-peak rate, the lower of two time-of-day tiers; peak (01:00-04:00 and 06:00-10:00 "
        "UTC on weekdays, Chinese public holidays excepted) is $1.32/$3.96.",
    ),

    "qwen3.8-max": Price(
        2.0, 6.0, _QWEN, "2026-11-07",
        "Singapore (International) rate; qwen-cn's China (Beijing) rate on the same page is "
        "$1.65/$4.951.",
    ),
    "qwen3.8-flash": Price(
        0.15, 0.47, _QWEN, "2026-11-07",
        "Singapore (International) rate; qwen-cn's China (Beijing) rate on the same page is "
        "$0.113/$0.382.",
    ),
    "qwen3.7-max": Price(
        2.5, 7.5, _QWEN, "2026-11-07",
        "Singapore (International) rate; currently equivalent to qwen3.7-max-2026-05-20.",
    ),
    "qwen3.7-plus": Price(
        0.4, 1.6, _QWEN, "2026-11-07",
        "Singapore (International) list price for prompts up to 256K tokens (256K-1M: "
        "$1.20/$4.80); the page shows a limited-time 20% discount on top, with no end date.",
    ),
    "qwen3.6-plus": Price(
        0.5, 3.0, _QWEN, "2026-11-07",
        "Singapore (International) rate for prompts up to 256K tokens; 256K-1M: $2/$6.",
    ),

    "glm-5.3": Price(
        1.4, 4.4, _ZAI, "2026-11-07",
        "Z.AI rate. BigModel (glm-cn) lists 8/28 CNY: $1.11/$3.89 at 7.2 CNY/USD.",
    ),
    "glm-5.3-flash": Price(
        0.15, 0.5, _ZAI, "2026-11-07",
        "Z.AI rate. BigModel (glm-cn) lists 0.8/2.8 CNY ($0.11/$0.39 at 7.2 CNY/USD) and "
        "advertises a limited-time 50% discount on it.",
    ),
    "glm-5.2": Price(
        1.4, 4.4, _ZAI, "2026-11-07",
        "Z.AI rate. BigModel (glm-cn) lists 8/28 CNY: $1.11/$3.89 at 7.2 CNY/USD.",
    ),
    "glm-5.1": Price(
        1.4, 4.4, _ZAI, "2026-11-07",
        "Z.AI rate. BigModel (glm-cn) lists 6/24 CNY for prompts under 32K tokens "
        "($0.83/$3.33 at 7.2 CNY/USD), 8/28 CNY above.",
    ),
    "glm-5-turbo": Price(
        5 / _CNY_PER_USD, 22 / _CNY_PER_USD, _BIGMODEL, "2026-11-07",
        "BigModel rate for prompts under 32K tokens (32K and up: 7/26 CNY), converted from "
        "5/22 CNY at 7.2 CNY/USD. Z.AI no longer lists GLM-5-Turbo on its pricing page.",
    ),
    "glm-4.7": Price(
        0.6, 2.2, _ZAI, "2026-11-07",
        "Z.AI rate. BigModel (glm-cn) tiers by prompt and output length; its lowest tier is "
        "2/8 CNY ($0.28/$1.11 at 7.2 CNY/USD).",
    ),
    "glm-4.5-air": Price(
        0.2, 1.1, _ZAI, "2026-11-07",
        "Z.AI rate. BigModel (glm-cn) tiers by prompt and output length; its lowest tier is "
        "0.8/2 CNY ($0.11/$0.28 at 7.2 CNY/USD).",
    ),

    "kimi-k3": Price(
        3.0, 15.0, "https://platform.kimi.ai/", "2026-11-07", "Flat rate, no context tiers.",
    ),
    "kimi-k2.6": Price(
        0.95, 4.0, "https://www.kimi.ai/resources/kimi-k2-6-pricing", "2026-11-07",
        "K2 models are closed to new users from 2026-10-31 and Moonshot plans to retire them "
        "by the end of December 2026.",
    ),

    "MiniMax-M3": Price(
        0.3, 1.2, _MINIMAX, "2026-11-07",
        "Standard tier for prompts up to 512K tokens (longer: $0.60/$2.40), after the page's "
        "permanent 50% discount on the $0.60/$2.40 list price. MiniMax China (minimax-cn) "
        "lists 2.10/8.40 CNY: $0.29/$1.17 at 7.2 CNY/USD.",
    ),

    "mistral-medium-2604": Price(
        1.5, 7.5, "https://docs.mistral.ai/models/mistral-medium-3-5-26-04", "2026-11-07",
        "Mistral Medium 3.5, version 26.04; its page lists the API names mistral-medium-3-5, "
        "mistral-medium-3 and mistral-medium-latest, not this dated id. Deprecated "
        "2026-10-31, retiring 2027-04-30.",
    ),
    "mistral-small-2603": Price(
        0.15, 0.6, "https://docs.mistral.ai/models/mistral-small-4-0-26-03", "2026-11-07",
        "Mistral Small 4, version 26.03.",
    ),

    "qwen3:latest": Price(
        0.0, 0.0, "https://ollama.com/library/qwen3", "2026-11-07",
        "Runs locally through Ollama, so no per-token charge; this tag is the 8B model.",
    ),
    "gpt-oss:latest": Price(
        0.0, 0.0, "https://ollama.com/library/gpt-oss", "2026-11-07",
        "Runs locally through Ollama, so no per-token charge; this tag is the 20B model.",
    ),
    "glm-4.7-flash:latest": Price(
        0.0, 0.0, "https://ollama.com/library/glm-4.7-flash", "2026-11-07",
        "Runs locally through Ollama, so no per-token charge; a 30B-A3B MoE model.",
    ),
}

_MINIMAX_M2_RETIRED = (
    "Checked 2026-11-07: MiniMax's model list marks it retired (closed to new users "
    "2026-10-19, retirement 2026-11-18) and neither MiniMax pricing page lists it."
)

UNPRICED: dict[str, str] = {
    "claude-mythos-preview": (
        "Checked 2026-11-07: a deprecated research preview with limited access; Anthropic's "
        "pricing page gives no rate for it."
    ),
    "gemini-3.5-flash": (
        "Checked 2026-11-07: the Gemini API routes requests for it to gemini-3.6-flash "
        "(deprecations page) and its pricing page no longer lists it; that page has "
        "gemini-3.6-flash at $0.75/$3.75 through 2026-12-31. Vertex AI still lists $1.50/$9.00 "
        "for its own endpoint."
    ),
    "qwen3.6-max": (
        "Checked 2026-11-07: not on the Model Studio pricing page. Alibaba's model page for it "
        "names qwen3.6-max-preview, which the pricing page no longer lists either."
    ),
    "MiniMax-M2.5": _MINIMAX_M2_RETIRED,
    "MiniMax-M2.5-highspeed": _MINIMAX_M2_RETIRED,
    "MiniMax-M2.7": _MINIMAX_M2_RETIRED,
    "MiniMax-M2.7-highspeed": _MINIMAX_M2_RETIRED,
}


def normalise(model_id: str) -> str:
    """Lower-case a model id, drop a leading "provider/" prefix and spell dots as dashes."""
    return model_id.lower().split("/", 1)[-1].replace(".", "-")


_BY_NORMALISED_ID = {normalise(model_id): price for model_id, price in OFFICIAL.items()}


def lookup(model_id: str) -> Price | None:
    """The official price of a model, or None when the table has none.

    The id is tried as given, then normalised, so "claude-sonnet-5.5" and
    "anthropic/claude-sonnet-5-5" both find claude-sonnet-5-5.
    """
    return OFFICIAL.get(model_id) or _BY_NORMALISED_ID.get(normalise(model_id))
