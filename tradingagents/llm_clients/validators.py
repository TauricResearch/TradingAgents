"""Model name validators for each provider."""

from .model_catalog import get_known_models


VALID_MODELS = {
    provider: models
    for provider, models in get_known_models().items()
    if provider not in ("ollama", "openrouter")
}


def validate_model(provider: str, model: str) -> bool:
    """Check if model name is valid for the given provider.

    For ollama, openrouter - any model is accepted.
    """
    provider_lower = provider.lower()

    if provider_lower in ("ollama", "openrouter", "minimax"):
        return True

    if provider_lower not in VALID_MODELS:
        return True

    return model in VALID_MODELS[provider_lower]
