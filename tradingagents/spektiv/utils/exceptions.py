"""
LLM Rate Limit Exception Hierarchy.

This module provides a unified exception hierarchy for handling rate limit errors
across different LLM providers (OpenAI, Anthropic, OpenRouter).

The exception hierarchy:
    Exception
        LLMRateLimitError (base class)
            OpenAIRateLimitError
            AnthropicRateLimitError
            OpenRouterRateLimitError

Each exception includes:
    - message: Human-readable error message
    - retry_after: Optional[int] - Seconds to wait before retrying
    - provider: str - The LLM provider that raised the error

Usage:
    from spektiv.utils.exceptions import from_provider_error

    try:
        # Make LLM API call
        response = client.chat.completions.create(...)
    except Exception as e:
        if e.__class__.__name__ == "RateLimitError":
            # Convert to unified exception
            unified_error = from_provider_error(e, provider="openai")
            raise unified_error
"""

from typing import Optional


class LLMRateLimitError(Exception):
    """
    Base exception for LLM rate limit errors.

    Attributes:
        message (str): Human-readable error message
        retry_after (Optional[int]): Seconds to wait before retrying
        provider (Optional[str]): The LLM provider that raised the error
    """

    def __init__(
        self,
        message: str,
        retry_after: Optional[int] = None,
        provider: Optional[str] = None,
    ):
        """
        Initialize a rate limit error.

        Args:
            message: Human-readable error message
            retry_after: Optional seconds to wait before retrying
            provider: Optional provider name (openai, anthropic, openrouter)
        """
        self.retry_after = retry_after
        self.provider = provider
        super().__init__(message)


class OpenAIRateLimitError(LLMRateLimitError):
    """
    OpenAI-specific rate limit error.

    Automatically sets provider='openai'.
    """

    def __init__(self, message: str, retry_after: Optional[int] = None):
        """
        Initialize an OpenAI rate limit error.

        Args:
            message: Human-readable error message
            retry_after: Optional seconds to wait before retrying
        """
        super().__init__(message, retry_after=retry_after, provider="openai")


class AnthropicRateLimitError(LLMRateLimitError):
    """
    Anthropic-specific rate limit error.

    Automatically sets provider='anthropic'.
    """

    def __init__(self, message: str, retry_after: Optional[int] = None):
        """
        Initialize an Anthropic rate limit error.

        Args:
            message: Human-readable error message
            retry_after: Optional seconds to wait before retrying
        """
        super().__init__(message, retry_after=retry_after, provider="anthropic")


class OpenRouterRateLimitError(LLMRateLimitError):
    """
    OpenRouter-specific rate limit error.

    Automatically sets provider='openrouter'.
    """

    def __init__(self, message: str, retry_after: Optional[int] = None):
        """
        Initialize an OpenRouter rate limit error.

        Args:
            message: Human-readable error message
            retry_after: Optional seconds to wait before retrying
        """
        super().__init__(message, retry_after=retry_after, provider="openrouter")


def from_provider_error(error, provider: str) -> LLMRateLimitError:
    """
    Convert a native provider error to a unified LLMRateLimitError.

    Extracts retry_after from response headers if available and creates
    the appropriate provider-specific exception.

    Args:
        error: The native provider error object (e.g., openai.RateLimitError)
        provider: The provider name ('openai', 'anthropic', 'openrouter')

    Returns:
        LLMRateLimitError: Provider-specific unified exception

    Raises:
        ValueError: If the error is not a rate limit error

    Example:
        try:
            response = client.chat.completions.create(...)
        except Exception as e:
            if e.__class__.__name__ == "RateLimitError":
                unified = from_provider_error(e, provider="openai")
                logger.error(f"Rate limit: retry in {unified.retry_after}s")
                raise unified
    """
    # Validate that this is a rate limit error
    if error.__class__.__name__ != "RateLimitError":
        raise ValueError(
            f"Not a rate limit error: {error.__class__.__name__}. "
            "This function only converts RateLimitError exceptions."
        )

    # Extract error message
    message = _extract_message(error)

    # Extract retry_after from response headers
    retry_after = _extract_retry_after(error)

    # Create provider-specific exception
    if provider == "openai":
        return OpenAIRateLimitError(message, retry_after=retry_after)
    elif provider == "anthropic":
        return AnthropicRateLimitError(message, retry_after=retry_after)
    elif provider == "openrouter":
        return OpenRouterRateLimitError(message, retry_after=retry_after)
    else:
        # Unknown provider - use base class
        return LLMRateLimitError(message, retry_after=retry_after, provider=provider)


def _extract_message(error) -> str:
    """
    Extract error message from provider error object.

    Args:
        error: The native provider error object

    Returns:
        str: The error message
    """
    # Try to get message attribute
    if hasattr(error, "message"):
        return str(error.message)

    # Fall back to __str__
    return str(error)


def _extract_retry_after(error) -> Optional[int]:
    """
    Extract retry_after value from error response headers.

    Args:
        error: The native provider error object

    Returns:
        Optional[int]: Retry after seconds, or None if not available
    """
    try:
        # Check if error has response object
        if not hasattr(error, "response") or error.response is None:
            return None

        # Check if response has headers
        if not hasattr(error.response, "headers") or error.response.headers is None:
            return None

        # Get retry-after header
        headers = error.response.headers
        retry_after = headers.get("retry-after") or headers.get("Retry-After")

        if retry_after is None:
            return None

        # Convert to int
        retry_after_int = int(retry_after)

        # Validate - must be non-negative
        if retry_after_int < 0:
            return None

        return retry_after_int

    except (ValueError, TypeError, AttributeError):
        # Invalid retry-after value or missing attributes
        return None
