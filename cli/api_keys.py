"""API key and endpoint validation for LLM providers."""

import os
from typing import Optional, Tuple
import httpx


# Map cloud providers to their required environment variables
PROVIDER_API_KEYS = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GEMINI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}

# Default endpoints for local providers
LOCAL_PROVIDER_DEFAULTS = {
    "ollama": ("OLLAMA_URL", "http://localhost:11434"),
    "lm studio": ("LM_STUDIO_URL", "http://localhost:1234"),
}


def get_api_key(provider: str) -> Optional[str]:
    """Get API key for a cloud provider, returns None if not set."""
    provider_lower = provider.lower()

    # Special case: OpenRouter can use OPENROUTER_API_KEY or OPENAI_API_KEY with sk-or- prefix
    if provider_lower == "openrouter":
        openrouter_key = os.getenv("OPENROUTER_API_KEY")
        if openrouter_key:
            return openrouter_key
        # Check if OPENAI_API_KEY is actually an OpenRouter key
        openai_key = os.getenv("OPENAI_API_KEY", "")
        if openai_key.startswith("sk-or-"):
            return openai_key
        return None

    env_var = PROVIDER_API_KEYS.get(provider_lower)
    if env_var is None:
        return None
    return os.getenv(env_var)


def get_local_endpoint(provider: str) -> Optional[str]:
    """Get the endpoint URL for a local provider."""
    provider_lower = provider.lower()
    if provider_lower not in LOCAL_PROVIDER_DEFAULTS:
        return None

    env_var, default_url = LOCAL_PROVIDER_DEFAULTS[provider_lower]
    return os.getenv(env_var, default_url)


def is_local_provider_running(provider: str) -> bool:
    """Check if a local provider (Ollama/LM Studio) is running by probing its endpoint."""
    endpoint = get_local_endpoint(provider)
    if not endpoint:
        return False

    try:
        # Probe the models endpoint with a short timeout
        response = httpx.get(
            f"{endpoint}/v1/models",
            timeout=1.0
        )
        return response.status_code == 200
    except (httpx.RequestError, httpx.TimeoutException):
        return False


def is_provider_available(provider: str) -> Tuple[bool, str]:
    """
    Check if a provider is available.

    Returns:
        Tuple of (is_available, reason_if_unavailable)
    """
    provider_lower = provider.lower()

    # Local providers: check if endpoint is reachable
    if provider_lower in LOCAL_PROVIDER_DEFAULTS:
        if is_local_provider_running(provider):
            return (True, "")
        return (False, "Not running")

    # Cloud providers: check for API key
    if get_api_key(provider) is not None:
        return (True, "")
    return (False, "No API key")


def get_all_provider_availability() -> dict:
    """
    Get availability status for all providers.

    Returns:
        Dict mapping provider name to (is_available, reason) tuple
    """
    all_providers = list(PROVIDER_API_KEYS.keys()) + list(LOCAL_PROVIDER_DEFAULTS.keys())
    return {provider: is_provider_available(provider) for provider in all_providers}
