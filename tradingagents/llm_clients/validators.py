from typing import Dict, List

VALID_MODELS: Dict[str, List[str]] = {
    "openai": [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
        "gpt-4",
        "gpt-3.5-turbo",
        "o1",
        "o1-mini",
        "o1-preview",
        "o3-mini",
        "gpt-5-nano",
        "gpt-5-mini",
        "gpt-5",
    ],
    "anthropic": [
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
        "claude-3-opus-20240229",
        "claude-3-sonnet-20240229",
        "claude-3-haiku-20240307",
        "claude-sonnet-4-20250514",
        "claude-haiku-4-5-20251001",
        "claude-opus-4-5-20251101",
    ],
    "google": [
        "gemini-1.5-pro",
        "gemini-1.5-flash",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-2.5-pro-preview-05-06",
        "gemini-2.5-flash-preview-05-20",
        "gemini-3-pro-preview",
        "gemini-3-flash-preview",
    ],
    "xai": [
        "grok-beta",
        "grok-2",
        "grok-2-mini",
        "grok-3",
        "grok-3-mini",
    ],
    "ollama": [],
    "openrouter": [],
    "vllm": [],
}


def validate_model(provider: str, model: str) -> bool:
    """Validate that a model is supported by the provider.

    For ollama, openrouter, and vllm, any model is accepted.
    For other providers, checks against VALID_MODELS.
    """
    provider_lower = provider.lower()

    if provider_lower in ("ollama", "openrouter", "vllm"):
        return True

    if provider_lower not in VALID_MODELS:
        return False

    valid = VALID_MODELS[provider_lower]
    if not valid:
        return True

    return model in valid
