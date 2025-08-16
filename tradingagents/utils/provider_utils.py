"""
Utility functions for LLM provider configuration and API key management.
"""

import os


def get_api_key_for_provider(config):
    """Get the appropriate API key based on the provider.

    Args:
        config (dict): Configuration dictionary containing llm_provider

    Returns:
        str: The API key for the provider, or None if not found
    """
    provider = config.get("llm_provider", "openai").lower()

    # Handle custom provider first
    if provider.startswith("custom"):
        api_key = os.getenv("CUSTOM_API_KEY")
        if not api_key:
            print("Warning: CUSTOM_API_KEY not found in environment variables")
        return api_key

    # Map providers to their environment variables
    api_key_mapping = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "google": "GOOGLE_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "ollama": "OLLAMA_API_KEY",
    }

    env_var = api_key_mapping.get(provider, "OPENAI_API_KEY")
    api_key = os.getenv(env_var)

    if not api_key and provider != "ollama":  # Ollama typically doesn't need API keys
        print(f"Warning: {env_var} not found in environment variables")

    return api_key


def get_openai_client(config):
    """Get a properly configured OpenAI client based on the provider configuration.

    This function centralizes OpenAI client creation with correct API key resolution
    for all providers that use OpenAI-compatible interfaces (OpenAI, OpenRouter,
    Ollama, and custom providers).

    Args:
        config (dict): Configuration dictionary containing llm_provider and backend_url

    Returns:
        OpenAI: Configured OpenAI client instance
    """
    from openai import OpenAI

    api_key = get_api_key_for_provider(config)
    backend_url = config.get("backend_url", "https://api.openai.com/v1")

    return OpenAI(base_url=backend_url, api_key=api_key)
