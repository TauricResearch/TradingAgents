"""
User-Facing Error Messages.

This module provides functions for formatting user-friendly error messages,
particularly for rate limit errors.

Functions:
    format_rate_limit_error: Format a rate limit error for user display
    format_error_with_partial_save: Format error with partial save location
    format_retry_time: Format retry time in human-readable format
    print_user_error: Print error to console in user-friendly format
"""

from typing import Optional

from spektiv.utils.exceptions import LLMRateLimitError

try:
    from rich.console import Console
    from rich.panel import Panel
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


def format_rate_limit_error(error: LLMRateLimitError) -> str:
    """
    Format a rate limit error for user display.

    Creates a user-friendly message that includes:
    - Provider name
    - Retry guidance
    - Retry time if available

    Args:
        error: LLMRateLimitError instance

    Returns:
        str: Formatted error message

    Example:
        >>> error = OpenAIRateLimitError("Rate limit exceeded", retry_after=60)
        >>> format_rate_limit_error(error)
        'Rate limit exceeded for OpenAI. Please retry in 60 seconds (1 minute).'
    """
    provider_name = _format_provider_name(error.provider)

    if error.retry_after is not None:
        retry_time = format_retry_time(error.retry_after)
        return (
            f"Rate limit exceeded for {provider_name}. "
            f"Please retry in {retry_time}."
        )
    else:
        return (
            f"Rate limit exceeded for {provider_name}. "
            f"Please wait a moment and try again later."
        )


def format_error_with_partial_save(error_message: str, partial_file: str) -> str:
    """
    Format error message with information about saved partial analysis.

    Args:
        error_message: The error message
        partial_file: Path to saved partial analysis file

    Returns:
        str: Formatted message

    Example:
        >>> format_error_with_partial_save(
        ...     "Rate limit exceeded",
        ...     "./results/partial_AAPL_20241226.json"
        ... )
        'Rate limit exceeded\\n\\nPartial analysis saved to: ./results/partial_AAPL_20241226.json'
    """
    return (
        f"{error_message}\n\n"
        f"Partial analysis saved to: {partial_file}\n"
        f"You can inspect the partial results and retry when the rate limit resets."
    )


def format_retry_time(seconds: int) -> str:
    """
    Format retry time in human-readable format.

    Converts seconds to appropriate units:
    - < 60s: "X seconds"
    - < 3600s: "X minutes (Y seconds)"
    - >= 3600s: "X hours (Y minutes)"

    Args:
        seconds: Number of seconds

    Returns:
        str: Human-readable time format

    Example:
        >>> format_retry_time(60)
        '1 minute (60 seconds)'
        >>> format_retry_time(300)
        '5 minutes (300 seconds)'
        >>> format_retry_time(3600)
        '1 hour (60 minutes)'
    """
    if seconds < 60:
        return f"{seconds} seconds"

    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ({seconds} seconds)"

    hours = minutes // 60
    remaining_minutes = minutes % 60
    return f"{hours} hour{'s' if hours != 1 else ''} ({remaining_minutes} minutes)"


def print_user_error(error: LLMRateLimitError) -> None:
    """
    Print error to console in user-friendly format.

    Uses Rich Panel if available, otherwise falls back to simple print.

    Args:
        error: LLMRateLimitError instance

    Example:
        >>> error = OpenAIRateLimitError("Rate limit exceeded", retry_after=60)
        >>> print_user_error(error)
        # Displays formatted error panel in terminal
    """
    message = format_rate_limit_error(error)

    if RICH_AVAILABLE:
        console = Console()
        panel = Panel(
            message,
            title="[bold red]Rate Limit Error[/bold red]",
            border_style="red",
        )
        console.print(panel)
    else:
        print(f"\n{'='*60}")
        print(f"RATE LIMIT ERROR")
        print(f"{'='*60}")
        print(message)
        print(f"{'='*60}\n")


def _format_provider_name(provider: Optional[str]) -> str:
    """
    Format provider name for display.

    Args:
        provider: Provider identifier

    Returns:
        str: Formatted provider name
    """
    if provider is None:
        return "LLM provider"

    # Capitalize provider names
    provider_names = {
        "openai": "OpenAI",
        "anthropic": "Anthropic",
        "openrouter": "OpenRouter",
    }

    return provider_names.get(provider.lower(), provider.title())
