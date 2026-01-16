"""Dynamic model fetching from LLM provider APIs with caching."""

import os
from typing import List, Tuple, Optional
import httpx

# Cache for fetched models (provider -> list of models)
_model_cache: dict = {}

# Maximum number of models to display (None = no limit, show all)
MAX_MODELS = None


def is_fetch_latest() -> bool:
    """Check if FETCH_LATEST is enabled in environment.

    When enabled, fetches models dynamically from provider APIs.
    When disabled, falls back to static hardcoded model lists.
    """
    return os.getenv("FETCH_LATEST", "false").lower() in ("true", "1", "yes")


def fetch_openai_models() -> Optional[List[Tuple[str, str]]]:
    """
    Fetch available models from OpenAI API, sorted by creation date (newest first).

    Returns:
        List of (display_name, model_id) tuples, or None on failure
    """
    if "openai" in _model_cache:
        return _model_cache["openai"]

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key.startswith("sk-or-"):
        return None

    try:
        response = httpx.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10.0
        )
        response.raise_for_status()
        models_data = response.json().get("data", [])

        # Filter to chat/reasoning models and keep metadata for sorting
        chat_models = []
        for model in models_data:
            model_id = model.get("id", "")
            created = model.get("created", 0)

            # Include GPT models and reasoning models (o-series)
            if (model_id.startswith("gpt-") or
                model_id.startswith("o1") or
                model_id.startswith("o3") or
                model_id.startswith("o4") or
                model_id.startswith("o5") or
                model_id.startswith("gpt-5")):
                # Skip snapshot/dated versions to keep list clean
                if "-20" not in model_id and "-preview" not in model_id.lower():
                    chat_models.append((model_id, created))

        # Remove duplicates (keep highest created timestamp for each model_id)
        model_dict = {}
        for model_id, created in chat_models:
            if model_id not in model_dict or created > model_dict[model_id]:
                model_dict[model_id] = created

        # Sort by created timestamp (newest first) and limit
        sorted_models = sorted(model_dict.items(), key=lambda x: -x[1])[:MAX_MODELS]
        result = [(model_id, model_id) for model_id, _ in sorted_models]

        _model_cache["openai"] = result
        return result
    except Exception:
        return None


def fetch_anthropic_models() -> Optional[List[Tuple[str, str]]]:
    """
    Fetch available models from Anthropic API, sorted by creation date (newest first).

    Returns:
        List of (display_name, model_id) tuples, or None on failure
    """
    if "anthropic" in _model_cache:
        return _model_cache["anthropic"]

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    try:
        response = httpx.get(
            "https://api.anthropic.com/v1/models",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01"
            },
            timeout=10.0
        )
        response.raise_for_status()
        models_data = response.json().get("data", [])

        # Filter to Claude models and keep metadata for sorting
        claude_models = []
        for model in models_data:
            model_id = model.get("id", "")
            # Anthropic API returns created_at as ISO string (RFC 3339)
            created_at = model.get("created_at", "")
            display_name = model.get("display_name", "")

            if model_id.startswith("claude-"):
                # Skip dated versions (e.g., claude-3-sonnet-20240229)
                if "-20" not in model_id:
                    # Use display_name if available, otherwise model_id
                    label = display_name if display_name else model_id
                    claude_models.append((model_id, label, created_at))

        # Remove duplicates (keep latest for each model_id)
        model_dict = {}
        for model_id, label, created_at in claude_models:
            if model_id not in model_dict or created_at > model_dict[model_id][1]:
                model_dict[model_id] = (label, created_at)

        # Sort by created_at (newest first) and limit
        sorted_models = sorted(model_dict.items(), key=lambda x: x[1][1], reverse=True)[:MAX_MODELS]
        result = [(label, model_id) for model_id, (label, _) in sorted_models]

        _model_cache["anthropic"] = result
        return result
    except Exception:
        return None


def fetch_google_models() -> Optional[List[Tuple[str, str]]]:
    """
    Fetch available models from Google Generative AI API.
    Uses displayName for user-friendly labels, sorted as returned by API (typically newest first).

    Returns:
        List of (display_name, model_id) tuples, or None on failure
    """
    if "google" in _model_cache:
        return _model_cache["google"]

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None

    try:
        response = httpx.get(
            f"https://generativelanguage.googleapis.com/v1/models?key={api_key}",
            timeout=10.0
        )
        response.raise_for_status()
        models_data = response.json().get("models", [])

        # Filter to Gemini models that support generateContent
        gemini_models = []
        for model in models_data:
            model_name = model.get("name", "")
            display_name = model.get("displayName", "")
            supported_methods = model.get("supportedGenerationMethods", [])

            # Extract model ID from "models/gemini-..." format
            if model_name.startswith("models/"):
                model_id = model_name.replace("models/", "")
            else:
                model_id = model_name

            # Only include Gemini models that support content generation
            if model_id.startswith("gemini") and "generateContent" in supported_methods:
                # Use displayName if available, otherwise model_id
                label = display_name if display_name else model_id
                gemini_models.append((label, model_id))

        # API returns in a reasonable order, just dedupe and limit
        seen = set()
        unique_models = []
        for label, model_id in gemini_models:
            if model_id not in seen:
                seen.add(model_id)
                unique_models.append((label, model_id))

        result = unique_models[:MAX_MODELS]

        _model_cache["google"] = result
        return result
    except Exception:
        return None


def fetch_models_for_provider(provider: str) -> Optional[List[Tuple[str, str]]]:
    """
    Fetch models for a given provider.

    Only fetches dynamically if FETCH_LATEST is enabled. Otherwise returns None
    to trigger fallback to static model lists.

    Args:
        provider: Provider name (openai, anthropic, google)

    Returns:
        List of (display_name, model_id) tuples, or None if not supported/failed
    """
    # Return None if FETCH_LATEST is not enabled - will use static lists
    if not is_fetch_latest():
        return None

    provider_lower = provider.lower()

    if provider_lower == "openai":
        return fetch_openai_models()
    elif provider_lower == "anthropic":
        return fetch_anthropic_models()
    elif provider_lower == "google":
        return fetch_google_models()

    return None


def clear_cache():
    """Clear the model cache."""
    _model_cache.clear()
