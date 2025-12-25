"""
Test suite for LLM Rate Limit Exception Hierarchy.

This module tests:
1. LLMRateLimitError base class creation with message and retry_after
2. Provider-specific exception classes (OpenAI, Anthropic, OpenRouter)
3. from_provider_error() conversion from native provider exceptions
4. Exception attribute validation (message, retry_after, provider)
5. Exception inheritance chain
"""

import pytest
from unittest.mock import Mock
from typing import Optional


# ============================================================================
# Test Utilities
# ============================================================================

def create_mock_openai_rate_limit_error(retry_after: Optional[int] = None):
    """Create a mock OpenAI RateLimitError for testing."""
    error = Mock()
    error.__class__.__name__ = "RateLimitError"
    error.message = "Rate limit exceeded for model gpt-4"

    # Mock response headers
    error.response = Mock()
    error.response.headers = {}
    if retry_after:
        error.response.headers["retry-after"] = str(retry_after)

    return error


def create_mock_anthropic_rate_limit_error(retry_after: Optional[int] = None):
    """Create a mock Anthropic RateLimitError for testing."""
    error = Mock()
    error.__class__.__name__ = "RateLimitError"
    error.message = "Your request has exceeded the rate limit"

    # Mock response with retry-after header
    error.response = Mock()
    error.response.headers = {}
    if retry_after:
        error.response.headers["retry-after"] = str(retry_after)

    return error


def create_mock_openrouter_rate_limit_error(retry_after: Optional[int] = None):
    """Create a mock OpenRouter RateLimitError (via OpenAI client) for testing."""
    error = Mock()
    error.__class__.__name__ = "RateLimitError"
    error.message = "Rate limit reached for anthropic/claude-opus-4.5"

    error.response = Mock()
    error.response.headers = {}
    if retry_after:
        error.response.headers["retry-after"] = str(retry_after)

    return error


# ============================================================================
# Test LLMRateLimitError Base Class
# ============================================================================

class TestLLMRateLimitError:
    """Test the base LLMRateLimitError exception class."""

    def test_basic_exception_creation(self):
        """Test creating LLMRateLimitError with just a message."""
        # Import will fail initially (TDD RED phase)
        from tradingagents.utils.exceptions import LLMRateLimitError

        error = LLMRateLimitError("Rate limit exceeded")

        assert str(error) == "Rate limit exceeded"
        assert error.retry_after is None
        assert error.provider is None

    def test_exception_with_retry_after(self):
        """Test LLMRateLimitError with retry_after parameter."""
        from tradingagents.utils.exceptions import LLMRateLimitError

        error = LLMRateLimitError("Rate limit exceeded", retry_after=60)

        assert str(error) == "Rate limit exceeded"
        assert error.retry_after == 60
        assert isinstance(error.retry_after, int)

    def test_exception_with_provider(self):
        """Test LLMRateLimitError with provider parameter."""
        from tradingagents.utils.exceptions import LLMRateLimitError

        error = LLMRateLimitError(
            "Rate limit exceeded",
            retry_after=120,
            provider="openai"
        )

        assert error.provider == "openai"
        assert error.retry_after == 120

    def test_exception_inheritance(self):
        """Test that LLMRateLimitError inherits from Exception."""
        from tradingagents.utils.exceptions import LLMRateLimitError

        error = LLMRateLimitError("Test")

        assert isinstance(error, Exception)
        assert isinstance(error, LLMRateLimitError)

    def test_exception_with_none_retry_after(self):
        """Test that retry_after can be None."""
        from tradingagents.utils.exceptions import LLMRateLimitError

        error = LLMRateLimitError("Rate limit", retry_after=None)

        assert error.retry_after is None


# ============================================================================
# Test Provider-Specific Exceptions
# ============================================================================

class TestOpenAIRateLimitError:
    """Test OpenAI-specific rate limit error."""

    def test_openai_exception_creation(self):
        """Test creating OpenAIRateLimitError."""
        from tradingagents.utils.exceptions import OpenAIRateLimitError, LLMRateLimitError

        error = OpenAIRateLimitError("OpenAI rate limit", retry_after=45)

        assert isinstance(error, LLMRateLimitError)
        assert str(error) == "OpenAI rate limit"
        assert error.retry_after == 45
        assert error.provider == "openai"

    def test_openai_exception_inherits_base(self):
        """Test that OpenAIRateLimitError inherits from LLMRateLimitError."""
        from tradingagents.utils.exceptions import OpenAIRateLimitError, LLMRateLimitError

        error = OpenAIRateLimitError("Test")

        assert isinstance(error, LLMRateLimitError)
        assert isinstance(error, Exception)


class TestAnthropicRateLimitError:
    """Test Anthropic-specific rate limit error."""

    def test_anthropic_exception_creation(self):
        """Test creating AnthropicRateLimitError."""
        from tradingagents.utils.exceptions import AnthropicRateLimitError, LLMRateLimitError

        error = AnthropicRateLimitError("Anthropic rate limit", retry_after=90)

        assert isinstance(error, LLMRateLimitError)
        assert str(error) == "Anthropic rate limit"
        assert error.retry_after == 90
        assert error.provider == "anthropic"

    def test_anthropic_exception_inherits_base(self):
        """Test that AnthropicRateLimitError inherits from LLMRateLimitError."""
        from tradingagents.utils.exceptions import AnthropicRateLimitError, LLMRateLimitError

        error = AnthropicRateLimitError("Test")

        assert isinstance(error, LLMRateLimitError)
        assert isinstance(error, Exception)


class TestOpenRouterRateLimitError:
    """Test OpenRouter-specific rate limit error."""

    def test_openrouter_exception_creation(self):
        """Test creating OpenRouterRateLimitError."""
        from tradingagents.utils.exceptions import OpenRouterRateLimitError, LLMRateLimitError

        error = OpenRouterRateLimitError("OpenRouter rate limit", retry_after=30)

        assert isinstance(error, LLMRateLimitError)
        assert str(error) == "OpenRouter rate limit"
        assert error.retry_after == 30
        assert error.provider == "openrouter"

    def test_openrouter_exception_inherits_base(self):
        """Test that OpenRouterRateLimitError inherits from LLMRateLimitError."""
        from tradingagents.utils.exceptions import OpenRouterRateLimitError, LLMRateLimitError

        error = OpenRouterRateLimitError("Test")

        assert isinstance(error, LLMRateLimitError)
        assert isinstance(error, Exception)


# ============================================================================
# Test from_provider_error() Conversion
# ============================================================================

class TestProviderErrorConversion:
    """Test conversion from native provider errors to unified exceptions."""

    def test_convert_openai_error_with_retry_after(self):
        """Test converting OpenAI RateLimitError with retry-after header."""
        from tradingagents.utils.exceptions import from_provider_error, OpenAIRateLimitError

        mock_error = create_mock_openai_rate_limit_error(retry_after=60)

        converted = from_provider_error(mock_error, provider="openai")

        assert isinstance(converted, OpenAIRateLimitError)
        assert converted.retry_after == 60
        assert converted.provider == "openai"
        assert "Rate limit exceeded" in str(converted)

    def test_convert_openai_error_without_retry_after(self):
        """Test converting OpenAI RateLimitError without retry-after header."""
        from tradingagents.utils.exceptions import from_provider_error, OpenAIRateLimitError

        mock_error = create_mock_openai_rate_limit_error(retry_after=None)

        converted = from_provider_error(mock_error, provider="openai")

        assert isinstance(converted, OpenAIRateLimitError)
        assert converted.retry_after is None
        assert converted.provider == "openai"

    def test_convert_anthropic_error_with_retry_after(self):
        """Test converting Anthropic RateLimitError with retry-after header."""
        from tradingagents.utils.exceptions import from_provider_error, AnthropicRateLimitError

        mock_error = create_mock_anthropic_rate_limit_error(retry_after=120)

        converted = from_provider_error(mock_error, provider="anthropic")

        assert isinstance(converted, AnthropicRateLimitError)
        assert converted.retry_after == 120
        assert converted.provider == "anthropic"

    def test_convert_anthropic_error_without_retry_after(self):
        """Test converting Anthropic RateLimitError without retry-after header."""
        from tradingagents.utils.exceptions import from_provider_error, AnthropicRateLimitError

        mock_error = create_mock_anthropic_rate_limit_error(retry_after=None)

        converted = from_provider_error(mock_error, provider="anthropic")

        assert isinstance(converted, AnthropicRateLimitError)
        assert converted.retry_after is None

    def test_convert_openrouter_error_with_retry_after(self):
        """Test converting OpenRouter RateLimitError with retry-after header."""
        from tradingagents.utils.exceptions import from_provider_error, OpenRouterRateLimitError

        mock_error = create_mock_openrouter_rate_limit_error(retry_after=45)

        converted = from_provider_error(mock_error, provider="openrouter")

        assert isinstance(converted, OpenRouterRateLimitError)
        assert converted.retry_after == 45
        assert converted.provider == "openrouter"

    def test_convert_openrouter_error_without_retry_after(self):
        """Test converting OpenRouter RateLimitError without retry-after header."""
        from tradingagents.utils.exceptions import from_provider_error, OpenRouterRateLimitError

        mock_error = create_mock_openrouter_rate_limit_error(retry_after=None)

        converted = from_provider_error(mock_error, provider="openrouter")

        assert isinstance(converted, OpenRouterRateLimitError)
        assert converted.retry_after is None

    def test_convert_unknown_provider(self):
        """Test converting error from unknown provider defaults to base class."""
        from tradingagents.utils.exceptions import from_provider_error, LLMRateLimitError

        mock_error = create_mock_openai_rate_limit_error(retry_after=30)

        converted = from_provider_error(mock_error, provider="unknown")

        # Should return base LLMRateLimitError for unknown providers
        assert isinstance(converted, LLMRateLimitError)
        assert converted.provider == "unknown"

    def test_convert_non_rate_limit_error(self):
        """Test that non-rate-limit errors are not converted."""
        from tradingagents.utils.exceptions import from_provider_error

        mock_error = Mock()
        mock_error.__class__.__name__ = "APIError"
        mock_error.message = "API connection failed"

        # Should return None or raise ValueError for non-rate-limit errors
        with pytest.raises(ValueError, match="Not a rate limit error"):
            from_provider_error(mock_error, provider="openai")

    def test_extract_retry_after_from_string(self):
        """Test extracting retry_after when it's a string in headers."""
        from tradingagents.utils.exceptions import from_provider_error, OpenAIRateLimitError

        mock_error = Mock()
        mock_error.__class__.__name__ = "RateLimitError"
        mock_error.message = "Rate limit exceeded"
        mock_error.response = Mock()
        mock_error.response.headers = {"retry-after": "75"}

        converted = from_provider_error(mock_error, provider="openai")

        assert isinstance(converted, OpenAIRateLimitError)
        assert converted.retry_after == 75
        assert isinstance(converted.retry_after, int)

    def test_extract_retry_after_from_int(self):
        """Test extracting retry_after when it's already an int in headers."""
        from tradingagents.utils.exceptions import from_provider_error, OpenAIRateLimitError

        mock_error = Mock()
        mock_error.__class__.__name__ = "RateLimitError"
        mock_error.message = "Rate limit exceeded"
        mock_error.response = Mock()
        mock_error.response.headers = {"retry-after": 90}

        converted = from_provider_error(mock_error, provider="openai")

        assert converted.retry_after == 90


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================

class TestExceptionEdgeCases:
    """Test edge cases and error handling in exception conversion."""

    def test_missing_response_object(self):
        """Test handling error with no response object."""
        from tradingagents.utils.exceptions import from_provider_error, OpenAIRateLimitError

        mock_error = Mock()
        mock_error.__class__.__name__ = "RateLimitError"
        mock_error.message = "Rate limit exceeded"
        mock_error.response = None

        converted = from_provider_error(mock_error, provider="openai")

        assert isinstance(converted, OpenAIRateLimitError)
        assert converted.retry_after is None

    def test_missing_headers_object(self):
        """Test handling error with response but no headers."""
        from tradingagents.utils.exceptions import from_provider_error, OpenAIRateLimitError

        mock_error = Mock()
        mock_error.__class__.__name__ = "RateLimitError"
        mock_error.message = "Rate limit exceeded"
        mock_error.response = Mock()
        mock_error.response.headers = None

        converted = from_provider_error(mock_error, provider="openai")

        assert isinstance(converted, OpenAIRateLimitError)
        assert converted.retry_after is None

    def test_invalid_retry_after_string(self):
        """Test handling invalid retry-after value (non-numeric string)."""
        from tradingagents.utils.exceptions import from_provider_error, OpenAIRateLimitError

        mock_error = Mock()
        mock_error.__class__.__name__ = "RateLimitError"
        mock_error.message = "Rate limit exceeded"
        mock_error.response = Mock()
        mock_error.response.headers = {"retry-after": "invalid"}

        converted = from_provider_error(mock_error, provider="openai")

        # Should gracefully handle invalid values
        assert isinstance(converted, OpenAIRateLimitError)
        assert converted.retry_after is None

    def test_negative_retry_after(self):
        """Test handling negative retry-after value."""
        from tradingagents.utils.exceptions import from_provider_error, OpenAIRateLimitError

        mock_error = Mock()
        mock_error.__class__.__name__ = "RateLimitError"
        mock_error.message = "Rate limit exceeded"
        mock_error.response = Mock()
        mock_error.response.headers = {"retry-after": "-10"}

        converted = from_provider_error(mock_error, provider="openai")

        # Should either convert to positive or set to None
        assert isinstance(converted, OpenAIRateLimitError)
        assert converted.retry_after is None or converted.retry_after >= 0

    def test_zero_retry_after(self):
        """Test handling zero retry-after value."""
        from tradingagents.utils.exceptions import from_provider_error, OpenAIRateLimitError

        mock_error = Mock()
        mock_error.__class__.__name__ = "RateLimitError"
        mock_error.message = "Rate limit exceeded"
        mock_error.response = Mock()
        mock_error.response.headers = {"retry-after": "0"}

        converted = from_provider_error(mock_error, provider="openai")

        assert isinstance(converted, OpenAIRateLimitError)
        assert converted.retry_after == 0

    def test_very_large_retry_after(self):
        """Test handling very large retry-after value."""
        from tradingagents.utils.exceptions import from_provider_error, OpenAIRateLimitError

        mock_error = Mock()
        mock_error.__class__.__name__ = "RateLimitError"
        mock_error.message = "Rate limit exceeded"
        mock_error.response = Mock()
        mock_error.response.headers = {"retry-after": "86400"}  # 24 hours

        converted = from_provider_error(mock_error, provider="openai")

        assert isinstance(converted, OpenAIRateLimitError)
        assert converted.retry_after == 86400

    def test_message_extraction_from_str(self):
        """Test extracting message when error has __str__ instead of message attribute."""
        from tradingagents.utils.exceptions import from_provider_error, OpenAIRateLimitError

        mock_error = Mock()
        mock_error.__class__.__name__ = "RateLimitError"
        mock_error.__str__ = Mock(return_value="Rate limit from __str__")
        del mock_error.message  # Remove message attribute
        mock_error.response = Mock()
        mock_error.response.headers = {}

        converted = from_provider_error(mock_error, provider="openai")

        assert isinstance(converted, OpenAIRateLimitError)
        assert "Rate limit from __str__" in str(converted)


# ============================================================================
# Integration Tests
# ============================================================================

class TestExceptionIntegration:
    """Test exception usage in realistic scenarios."""

    def test_catch_and_reraise_pattern(self):
        """Test the typical catch-and-reraise pattern."""
        from tradingagents.utils.exceptions import from_provider_error, OpenAIRateLimitError

        mock_error = create_mock_openai_rate_limit_error(retry_after=60)

        try:
            converted = from_provider_error(mock_error, provider="openai")
            raise converted
        except OpenAIRateLimitError as e:
            assert e.retry_after == 60
            assert e.provider == "openai"

    def test_exception_in_except_block(self):
        """Test using from_provider_error in an except block."""
        from tradingagents.utils.exceptions import from_provider_error, LLMRateLimitError

        mock_error = create_mock_openai_rate_limit_error(retry_after=45)

        try:
            # Simulate catching a provider error
            raise Exception("Simulated OpenAI error")
        except Exception:
            # Convert to our exception
            converted = from_provider_error(mock_error, provider="openai")
            assert isinstance(converted, LLMRateLimitError)

    def test_multiple_provider_errors(self):
        """Test handling errors from multiple providers in sequence."""
        from tradingagents.utils.exceptions import (
            from_provider_error,
            OpenAIRateLimitError,
            AnthropicRateLimitError,
            OpenRouterRateLimitError
        )

        openai_error = create_mock_openai_rate_limit_error(retry_after=30)
        anthropic_error = create_mock_anthropic_rate_limit_error(retry_after=60)
        openrouter_error = create_mock_openrouter_rate_limit_error(retry_after=90)

        openai_converted = from_provider_error(openai_error, provider="openai")
        anthropic_converted = from_provider_error(anthropic_error, provider="anthropic")
        openrouter_converted = from_provider_error(openrouter_error, provider="openrouter")

        assert isinstance(openai_converted, OpenAIRateLimitError)
        assert isinstance(anthropic_converted, AnthropicRateLimitError)
        assert isinstance(openrouter_converted, OpenRouterRateLimitError)

        assert openai_converted.retry_after == 30
        assert anthropic_converted.retry_after == 60
        assert openrouter_converted.retry_after == 90
