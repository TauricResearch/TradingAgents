"""Provider catalog + API-key presence for the configure form.

Key status is presence-only (``present`` / ``missing`` / ``not-required`` /
``optional``) — never values, never masked prefixes. No endpoint accepts a
key; keys live in ``.env`` and the UI names the env var to set.
"""

from __future__ import annotations

import os
from typing import Any

from tradingagents.llm_clients.api_key_env import get_api_key_env
from tradingagents.llm_clients.model_catalog import MODEL_OPTIONS

# (display name, provider key), mirroring cli.utils._llm_provider_table but
# without the endpoint URLs — the browser never needs backend URLs.
PROVIDERS: list[tuple[str, str]] = [
    ("OpenAI", "openai"),
    ("Google", "google"),
    ("Anthropic", "anthropic"),
    ("xAI", "xai"),
    ("DeepSeek", "deepseek"),
    ("Qwen", "qwen"),
    ("GLM", "glm"),
    ("MiniMax", "minimax"),
    ("OpenRouter", "openrouter"),
    ("Mistral", "mistral"),
    ("Kimi (Moonshot)", "kimi"),
    ("Groq", "groq"),
    ("NVIDIA NIM", "nvidia"),
    ("Azure OpenAI", "azure"),
    ("Amazon Bedrock", "bedrock"),
    ("Ollama", "ollama"),
    ("OpenAI-compatible (vLLM, LM Studio, llama.cpp, custom relay)", "openai_compatible"),
]

PROVIDER_KEYS = frozenset(key for _, key in PROVIDERS)


def _key_optional(provider: str) -> bool:
    from tradingagents.llm_clients.openai_client import OPENAI_COMPATIBLE_PROVIDERS

    spec = OPENAI_COMPATIBLE_PROVIDERS.get(provider)
    return spec is not None and spec.key_optional


def key_status(provider: str) -> tuple[str, str | None]:
    """Return (status, env_var) for a provider's API key. Never the value."""
    env_var = get_api_key_env(provider)
    if env_var is None:
        return "not-required", None
    if os.environ.get(env_var):
        return "present", env_var
    if _key_optional(provider):
        return "optional", env_var
    return "missing", env_var


def provider_catalog() -> list[dict[str, Any]]:
    catalog = []
    for display, key in PROVIDERS:
        status, env_var = key_status(key)
        models = MODEL_OPTIONS.get(key, {})
        catalog.append({
            "key": key,
            "display": display,
            "key_status": status,
            "key_env_var": env_var,
            "models": {
                mode: [{"label": label, "value": value} for label, value in options]
                for mode, options in models.items()
            },
            "needs_backend_url": key == "openai_compatible",
        })
    return catalog


def missing_key_error(provider: str) -> str | None:
    """Human-readable pre-run key validation error, or None if runnable."""
    status, env_var = key_status(provider)
    if status == "missing":
        return (
            f"API key for provider '{provider}' is not set. Add "
            f"{env_var}=<your key> to your .env file and restart the server."
        )
    return None
