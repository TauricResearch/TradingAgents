"""Model name validators for Anthropic Claude."""

VALID_MODELS = {
    "anthropic": [
        # Claude 4.6 series (latest)
        "claude-opus-4-6",
        "claude-sonnet-4-6",
        # Claude 4.5 series
        "claude-opus-4-5",
        "claude-sonnet-4-5",
        "claude-haiku-4-5",
    ],
}


def validate_model(provider: str, model: str) -> bool:
    """Check if model name is valid for the given provider."""
    provider_lower = provider.lower()

    if provider_lower not in VALID_MODELS:
        return True

    return model in VALID_MODELS[provider_lower]
