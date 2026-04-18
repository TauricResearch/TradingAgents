"""Model name validators for each provider.

Only validates model names - does NOT enforce limits.
Let LLM providers use their own defaults for unspecified params.
"""

VALID_MODELS = {
    "openai": [
        # GPT-5 series (2025)
        "gpt-5.2",
        "gpt-5.1",
        "gpt-5",
        "gpt-5-mini",
        "gpt-5-nano",
        # GPT-4.1 series (2025)
        "gpt-4.1",
        "gpt-4.1-mini",
        "gpt-4.1-nano",
        # o-series reasoning models
        "o4-mini",
        "o3",
        "o3-mini",
        "o1",
        "o1-preview",
        # GPT-4o series (legacy but still supported)
        "gpt-4o",
        "gpt-4o-mini",
    ],
    "anthropic": [
        # Claude 4.5 series (2025)
        "claude-opus-4-5",
        "claude-sonnet-4-5",
        "claude-haiku-4-5",
        # Claude 4.x series
        "claude-opus-4-1-20250805",
        "claude-sonnet-4-20250514",
        # Claude 3.7 series
        "claude-3-7-sonnet-20250219",
        # Claude 3.5 series (legacy)
        "claude-3-5-haiku-20241022",
        "claude-3-5-sonnet-20241022",
    ],
    "google": [
        # Gemini 3 series (preview)
        "gemini-3-pro-preview",
        "gemini-3-flash-preview",
        # Gemini 2.5 series
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        # Gemini 2.0 series
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
    ],
    "xai": [
        # Grok 4.1 series
        "grok-4-1-fast",
        "grok-4-1-fast-reasoning",
        "grok-4-1-fast-non-reasoning",
        # Grok 4 series
        "grok-4",
        "grok-4-0709",
        "grok-4-fast-reasoning",
        "grok-4-fast-non-reasoning",
    ],
    "groq": [
        # Llama 4 series
        "meta-llama/llama-4-maverick-17b-128e-instruct",
        "meta-llama/llama-4-scout-17b-16e-instruct",
        # Llama 3.3 series
        "llama-3.3-70b-versatile",
        "llama-3.3-70b-specdec",
        # Llama 3.1 series
        "llama-3.1-8b-instant",
        # Mixtral
        "mixtral-8x7b-32768",
        # DeepSeek
        "deepseek-r1-distill-llama-70b",
        # Gemma
        "gemma2-9b-it",
    ],
    "together": [
        # Llama 4 series
        "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8",
        "meta-llama/Llama-4-Scout-17B-16E-Instruct",
        # Llama 3.3 series
        "meta-llama/Meta-Llama-3.3-70B-Instruct-Turbo",
        # DeepSeek
        "deepseek-ai/DeepSeek-R1",
        "deepseek-ai/DeepSeek-V3",
        # Qwen
        "Qwen/Qwen2.5-72B-Instruct-Turbo",
        "Qwen/QwQ-32B",
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
