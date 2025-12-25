"""
Graph Error Translation Layer.

This module provides error translation from native LLM provider errors
to unified TradingAgents exceptions. This allows the graph to handle
errors consistently regardless of the underlying LLM provider.

Functions:
    translate_llm_error: Convert provider-specific errors to unified exceptions
"""

from typing import Any

from tradingagents.utils.exceptions import (
    from_provider_error,
    LLMRateLimitError,
)


def translate_llm_error(error: Any, provider: str) -> LLMRateLimitError:
    """
    Translate a native LLM provider error to a unified exception.

    This function serves as the integration point between the graph layer
    and the exception handling system. It converts provider-specific errors
    to our unified exception hierarchy.

    Args:
        error: Native provider error object
        provider: Provider name ('openai', 'anthropic', 'openrouter')

    Returns:
        LLMRateLimitError: Unified exception

    Raises:
        ValueError: If the error is not a rate limit error

    Example:
        try:
            response = llm_client.invoke(...)
        except Exception as e:
            if e.__class__.__name__ == "RateLimitError":
                unified_error = translate_llm_error(e, provider="openai")
                raise unified_error
            raise
    """
    return from_provider_error(error, provider=provider)
