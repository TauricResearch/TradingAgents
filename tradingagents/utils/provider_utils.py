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
