"""Model name validators for each provider.

Only validates model names - does NOT enforce limits.
Let LLM providers use their own defaults for unspecified params.
"""

VALID_MODELS = {
    "openai": [
        # GPT-5.4 series (2026)
        "gpt-5.4",
        "gpt-5.4-mini",
        "gpt-5.4-nano",
        # GPT-5 series (2025)
        "gpt-5",
        "gpt-5-mini",
        "gpt-5-nano",
        # GPT-4.1 (legacy but still supported)
        "gpt-4.1",
        # o-series reasoning models
        "o4-mini",
        "o3",
        "o3-pro",
        "o3-mini",
        "o1",
        "o1-pro",
    ],
    "anthropic": [
        # Claude 4.7 series (2026)
        "claude-opus-4-7",
        # Claude 4.6 series (2026)
        "claude-opus-4-6",
        "claude-sonnet-4-6",
        # Claude 4.5 series (2025)
        "claude-opus-4-5",
        "claude-sonnet-4-5",
        "claude-haiku-4-5",
        "claude-haiku-4-5-20251001",
        # Claude 4.x series (deprecated, retiring June 2026)
        "claude-opus-4-1-20250805",
        "claude-sonnet-4-20250514",
    ],
    "google": [
        # Gemini 3.1 series (2026)
        "gemini-3.1-pro-preview",
        "gemini-3.1-flash-lite-preview",
        # Gemini 3 series
        "gemini-3-flash-preview",
        # Gemini 2.5 series
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
    ],
    "xai": [
        # Grok 4.20 series (2026)
        "grok-4.20-0309-reasoning",
        "grok-4.20-0309-non-reasoning",
        "grok-4.20-multi-agent-0309",
        # Grok 4.1 series
        "grok-4-1-fast-reasoning",
        "grok-4-1-fast-non-reasoning",
    ],
    "groq": [
        # GPT-OSS series
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        # Llama 4 series
        "meta-llama/llama-4-scout-17b-16e-instruct",
        # Llama 3.x series
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        # Qwen
        "qwen/qwen3-32b",
    ],
    "together": [
        # Llama 4 series
        "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8",
        "meta-llama/Llama-4-Scout-17B-16E-Instruct",
        # DeepSeek
        "deepseek-ai/DeepSeek-V3.1",
        "deepseek-ai/DeepSeek-R1",
        # Qwen
        "Qwen/Qwen3.5-397B-A17B",
        "Qwen/Qwen3.5-9B",
        # Llama 3.3 series
        "meta-llama/Meta-Llama-3.3-70B-Instruct-Turbo",
    ],
}


def validate_model(provider: str, model: str) -> bool:
    """Check if model name is valid for the given provider.

    For ollama, openrouter - any model is accepted.
    """
    provider_lower = provider.lower()

    if provider_lower in ("ollama", "openrouter", "groq", "together"):
        return True

    if provider_lower not in VALID_MODELS:
        return True

    return model in VALID_MODELS[provider_lower]
