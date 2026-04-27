"""Model name validators for supported LLM providers."""

VALID_MODELS = {
    "anthropic": [
        # Claude 4.6 series (latest)
        "claude-opus-4-6",
        "claude-sonnet-4-6"

    ],
    # These are the actual model names supported by the chiasegpu.vn proxy.
    # Add any other models your API key has access to here.
    "openai": [
        "gpt-5.3-codex-high",
        "claude-opus-4-6",
        "claude-sonnet-4-6",
    ],
}


def validate_model(provider: str, model: str) -> bool:
    """Check if model name is valid for the given provider."""
    provider_lower = provider.lower()

    if provider_lower not in VALID_MODELS:
        return True

    return model in VALID_MODELS[provider_lower]
