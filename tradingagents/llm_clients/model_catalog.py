"""Shared model catalog for CLI selections and validation."""

from __future__ import annotations

from typing import Dict, List, Tuple

ModelOption = Tuple[str, str]
ProviderModeOptions = Dict[str, Dict[str, List[ModelOption]]]

# (display_label, tier_key, quick_model, deep_model)
ModelTier = Tuple[str, str, str, str]


MODEL_OPTIONS: ProviderModeOptions = {
    "openai": {
        "quick": [
            ("GPT-5.4 Mini - Fast, strong coding and tool use", "gpt-5.4-mini"),
            ("GPT-5.4 Nano - Cheapest, high-volume tasks", "gpt-5.4-nano"),
            ("GPT-5.4 - Latest frontier, 1M context", "gpt-5.4"),
            ("GPT-4.1 - Smartest non-reasoning model", "gpt-4.1"),
        ],
        "deep": [
            ("GPT-5.5 - Premium frontier reasoning", "gpt-5.5"),
            ("GPT-5.4 - Latest frontier, 1M context", "gpt-5.4"),
            ("GPT-5.2 - Strong reasoning, cost-effective", "gpt-5.2"),
            ("GPT-5.4 Mini - Fast, strong coding and tool use", "gpt-5.4-mini"),
            ("GPT-5.4 Pro - Most capable, expensive ($30/$180 per 1M tokens)", "gpt-5.4-pro"),
        ],
    },
    "anthropic": {
        "quick": [
            ("Claude Sonnet 4.6 - Best speed and intelligence balance", "claude-sonnet-4-6"),
            ("Claude Haiku 4.5 - Fast, near-instant responses", "claude-haiku-4-5"),
            ("Claude Sonnet 4.5 - Agents and coding", "claude-sonnet-4-5"),
        ],
        "deep": [
            ("Claude Opus 4.6 - Most intelligent, agents and coding", "claude-opus-4-6"),
            ("Claude Opus 4.5 - Premium, max intelligence", "claude-opus-4-5"),
            ("Claude Sonnet 4.6 - Best speed and intelligence balance", "claude-sonnet-4-6"),
            ("Claude Sonnet 4.5 - Agents and coding", "claude-sonnet-4-5"),
        ],
    },
    "google": {
        "quick": [
            ("Gemini 3 Flash - Next-gen fast", "gemini-3-flash-preview"),
            ("Gemini 2.5 Flash - Balanced, stable", "gemini-2.5-flash"),
            ("Gemini 3.1 Flash Lite - Most cost-efficient", "gemini-3.1-flash-lite-preview"),
            ("Gemini 2.5 Flash Lite - Fast, low-cost", "gemini-2.5-flash-lite"),
        ],
        "deep": [
            ("Gemini 3.1 Pro - Reasoning-first, complex workflows", "gemini-3.1-pro-preview"),
            ("Gemini 3 Flash - Next-gen fast", "gemini-3-flash-preview"),
            ("Gemini 2.5 Pro - Stable pro model", "gemini-2.5-pro"),
            ("Gemini 2.5 Flash - Balanced, stable", "gemini-2.5-flash"),
        ],
    },
    "xai": {
        "quick": [
            ("Grok 4.1 Fast (Non-Reasoning) - Speed optimized, 2M ctx", "grok-4-1-fast-non-reasoning"),
            ("Grok 4 Fast (Non-Reasoning) - Speed optimized", "grok-4-fast-non-reasoning"),
            ("Grok 4.1 Fast (Reasoning) - High-performance, 2M ctx", "grok-4-1-fast-reasoning"),
        ],
        "deep": [
            ("Grok 4 - Flagship model", "grok-4-0709"),
            ("Grok 4.1 Fast (Reasoning) - High-performance, 2M ctx", "grok-4-1-fast-reasoning"),
            ("Grok 4 Fast (Reasoning) - High-performance", "grok-4-fast-reasoning"),
            ("Grok 4.1 Fast (Non-Reasoning) - Speed optimized, 2M ctx", "grok-4-1-fast-non-reasoning"),
        ],
    },
    "deepseek": {
        "quick": [
            ("DeepSeek V4 Flash-Instant - Fastest, lowest cost", "deepseek-v4-flash-instant"),
            ("DeepSeek V4 Flash-Thinking - Balanced speed/quality", "deepseek-v4-flash-thinking"),
            ("DeepSeek V4 Pro - Most capable", "deepseek-v4-pro"),
            ("Custom model ID", "custom"),
        ],
        "deep": [
            ("DeepSeek V4 Pro - Most capable", "deepseek-v4-pro"),
            ("DeepSeek V4 Flash-Thinking - Balanced speed/quality", "deepseek-v4-flash-thinking"),
            ("DeepSeek V4 Flash-Instant - Fastest, lowest cost", "deepseek-v4-flash-instant"),
            ("Custom model ID", "custom"),
        ],
    },
    "qwen": {
        "quick": [
            ("Qwen 3.5 Flash", "qwen3.5-flash"),
            ("Qwen Plus", "qwen-plus"),
            ("Custom model ID", "custom"),
        ],
        "deep": [
            ("Qwen 3.6 Plus", "qwen3.6-plus"),
            ("Qwen 3.5 Plus", "qwen3.5-plus"),
            ("Qwen 3 Max", "qwen3-max"),
            ("Custom model ID", "custom"),
        ],
    },
    "glm": {
        "quick": [
            ("GLM-4.7", "glm-4.7"),
            ("GLM-5", "glm-5"),
            ("Custom model ID", "custom"),
        ],
        "deep": [
            ("GLM-5.1", "glm-5.1"),
            ("GLM-5", "glm-5"),
            ("Custom model ID", "custom"),
        ],
    },
    # OpenRouter models are fetched dynamically at CLI runtime.
    # No static entries needed; any model ID is accepted by the validator.
    "ollama": {
        "quick": [
            ("Qwen3:latest (8B, local)", "qwen3:latest"),
            ("GPT-OSS:latest (20B, local)", "gpt-oss:latest"),
            ("GLM-4.7-Flash:latest (30B, local)", "glm-4.7-flash:latest"),
        ],
        "deep": [
            ("GLM-4.7-Flash:latest (30B, local)", "glm-4.7-flash:latest"),
            ("GPT-OSS:latest (20B, local)", "gpt-oss:latest"),
            ("Qwen3:latest (8B, local)", "qwen3:latest"),
        ],
    },
}


MODEL_TIERS: Dict[str, List[ModelTier]] = {
    "openai": [
        ("Budget   — gpt-5.4-nano (quick) + gpt-5.4-mini (deep)",  "budget",   "gpt-5.4-nano",               "gpt-5.4-mini"),
        ("Standard — gpt-5.4-mini (quick) + gpt-5.4 (deep)",       "standard", "gpt-5.4-mini",               "gpt-5.4"),
        ("Premium  — gpt-5.4 (quick) + gpt-5.5 (deep)",            "premium",  "gpt-5.4",                    "gpt-5.5"),
    ],
    "anthropic": [
        ("Budget   — haiku-4-5 (quick) + sonnet-4-6 (deep)",       "budget",   "claude-haiku-4-5",           "claude-sonnet-4-6"),
        ("Standard — sonnet-4-6 (quick) + opus-4-6 (deep)",        "standard", "claude-sonnet-4-6",          "claude-opus-4-6"),
        ("Premium  — opus-4-6 × 2 (both roles)",                   "premium",  "claude-opus-4-6",            "claude-opus-4-6"),
    ],
    "google": [
        ("Budget   — 2.5-flash-lite (quick) + 2.5-flash (deep)",   "budget",   "gemini-2.5-flash-lite",      "gemini-2.5-flash"),
        ("Standard — 2.5-flash (quick) + 2.5-pro (deep)",          "standard", "gemini-2.5-flash",           "gemini-2.5-pro"),
        ("Premium  — 3-flash (quick) + 3.1-pro (deep)",            "premium",  "gemini-3-flash-preview",     "gemini-3.1-pro-preview"),
    ],
    "xai": [
        ("Budget   — grok-4.1-fast-non-reasoning × 2",             "budget",   "grok-4-1-fast-non-reasoning", "grok-4-1-fast-non-reasoning"),
        ("Standard — grok-4.1-fast-non-reasoning + grok-4",        "standard", "grok-4-1-fast-non-reasoning", "grok-4-0709"),
        ("Premium  — grok-4.1-fast-reasoning + grok-4",            "premium",  "grok-4-1-fast-reasoning",     "grok-4-0709"),
    ],
    "ollama": [
        ("Budget   — qwen3:latest × 2",                            "budget",   "qwen3:latest",               "qwen3:latest"),
        ("Standard — qwen3:latest (quick) + glm-4.7-flash (deep)", "standard", "qwen3:latest",               "glm-4.7-flash:latest"),
        ("Premium  — gpt-oss:latest (quick) + glm-4.7-flash (deep)", "premium", "gpt-oss:latest",            "glm-4.7-flash:latest"),
    ],
    "deepseek": [
        ("Budget   — flash-instant × 2",                           "budget",   "deepseek-v4-flash-instant",  "deepseek-v4-flash-instant"),
        ("Standard — flash-instant (quick) + flash-thinking (deep)", "standard", "deepseek-v4-flash-instant", "deepseek-v4-flash-thinking"),
        ("Premium  — flash-thinking (quick) + v4-pro (deep)",      "premium",  "deepseek-v4-flash-thinking", "deepseek-v4-pro"),
    ],
    "qwen": [
        ("Budget   — qwen-plus × 2",                               "budget",   "qwen-plus",                  "qwen-plus"),
        ("Standard — qwen3.5-flash (quick) + qwen3.5-plus (deep)", "standard", "qwen3.5-flash",             "qwen3.5-plus"),
        ("Premium  — qwen-plus (quick) + qwen3-max (deep)",        "premium",  "qwen-plus",                  "qwen3-max"),
    ],
    "glm": [
        ("Budget   — glm-4.7 × 2",                                  "budget",   "glm-4.7",                   "glm-4.7"),
        ("Standard — glm-4.7 (quick) + glm-5 (deep)",               "standard", "glm-4.7",                   "glm-5"),
        ("Premium  — glm-5 (quick) + glm-5.1 (deep)",              "premium",  "glm-5",                     "glm-5.1"),
    ],
}


def get_model_options(provider: str, mode: str) -> List[ModelOption]:
    """Return shared model options for a provider and selection mode."""
    return MODEL_OPTIONS[provider.lower()][mode]


def get_model_tiers(provider: str) -> List[ModelTier]:
    """Return tier presets (display, key, quick_model, deep_model) for a provider."""
    return MODEL_TIERS.get(provider.lower(), [])


def get_known_models() -> Dict[str, List[str]]:
    """Build known model names from the shared CLI catalog."""
    return {
        provider: sorted(
            {
                value
                for options in mode_options.values()
                for _, value in options
            }
        )
        for provider, mode_options in MODEL_OPTIONS.items()
    }
