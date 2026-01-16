"""Utility functions for model detection and selection."""

# Model prefixes that require the OpenAI Responses API (/v1/responses)
# instead of the Chat Completions API (/v1/chat/completions)
RESPONSES_API_PREFIXES = [
    "gpt-5",      # All GPT-5 variants (gpt-5, gpt-5.1, gpt-5.1-codex-mini, etc.)
    "codex",      # Codex models that use Responses API
]


def requires_responses_api(model_name: str) -> bool:
    """Check if a model requires the Responses API instead of Chat Completions.

    Some newer OpenAI models only support the /v1/responses endpoint and will
    return a 404 error if called via /v1/chat/completions.

    Args:
        model_name: The model identifier (e.g., "gpt-5.1-codex-mini", "gpt-4o")

    Returns:
        True if the model requires the Responses API, False otherwise.
    """
    model_lower = model_name.lower()
    return any(prefix in model_lower for prefix in RESPONSES_API_PREFIXES)
