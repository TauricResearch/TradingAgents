"""Model name validators for each provider."""

from .model_catalog import get_known_models


CUSTOM_MODEL_PROVIDERS = ("ollama", "openrouter", "lm-studio", "llama-cpp")


VALID_MODELS = {
    provider: models
    for provider, models in get_known_models().items()
    if provider not in CUSTOM_MODEL_PROVIDERS
}


def validate_model(provider: str, model: str) -> bool:
    """Check if model name is valid for the given provider.

    For providers backed by user-managed model catalogs, any model is accepted.
    """
    provider_lower = provider.lower()

    if provider_lower in CUSTOM_MODEL_PROVIDERS:
        return True

    if provider_lower not in VALID_MODELS:
        return True

    return model in VALID_MODELS[provider_lower]
