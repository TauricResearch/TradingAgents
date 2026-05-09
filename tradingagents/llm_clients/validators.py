"""Model name validators for each provider."""

from .model_catalog import get_known_models

# Providers where any model name is accepted (local runtimes with
# user-pulled models, dynamic catalogs, etc.).
_PERMISSIVE_PROVIDERS = ("ollama", "openrouter", "mlx")

VALID_MODELS = {
    provider: models for provider, models in get_known_models().items() if provider not in _PERMISSIVE_PROVIDERS
}


def validate_model(provider: str, model: str) -> bool:
    """Check if model name is valid for the given provider.

    For ollama, openrouter, mlx - any model is accepted.
    """
    provider_lower = provider.lower()

    if provider_lower in _PERMISSIVE_PROVIDERS:
        return True

    if provider_lower not in VALID_MODELS:
        return True

    return model in VALID_MODELS[provider_lower]
