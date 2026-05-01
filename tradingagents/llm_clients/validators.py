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
    
    Args:
        provider: LLM provider name (openai, anthropic, google, etc.)
        model: Model name to validate
        
    Returns:
        True if model is valid for provider
        
    Raises:
        ValueError: If provider is unknown (not ollama, openrouter, or in VALID_MODELS)
    """
    provider_lower = provider.lower()

    if provider_lower in ("ollama", "openrouter"):
        return True

    if provider_lower not in VALID_MODELS:
        valid_providers = list(VALID_MODELS.keys()) + ["ollama", "openrouter"]
        raise ValueError(
            f"Unknown provider '{provider}'. Valid providers: {valid_providers}"
        )

    return model in VALID_MODELS[provider_lower]
