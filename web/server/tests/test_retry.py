"""Unit tests for web.server.retry — pure-function helpers."""
from __future__ import annotations

import pytest

from web.server.retry import detect_rate_limit


class TestDetectRateLimit:
    def test_google_resource_exhausted(self):
        exc = Exception(
            "Error calling model 'gemini-3.5-flash' (RESOURCE_EXHAUSTED): 429 RESOURCE_EXHAUSTED. "
            "'retryDelay': '46s'"
        )
        assert detect_rate_limit(exc) is True

    def test_openai_rate_limit_error_class(self):
        class RateLimitError(Exception):
            pass
        assert detect_rate_limit(RateLimitError("Rate limit reached for gpt-4")) is True

    def test_anthropic_rate_limit_error_class(self):
        class AnthropicRateLimitError(Exception):
            pass
        assert detect_rate_limit(AnthropicRateLimitError("rate limit exceeded")) is True

    def test_openrouter_code_429_passthrough(self):
        exc = Exception('{"error": {"code": 429, "message": "rate-limited"}}')
        assert detect_rate_limit(exc) is True

    def test_openrouter_type_rate_limit_passthrough(self):
        exc = Exception('{"error": {"type": "rate_limit", "message": "Too Many Requests"}}')
        assert detect_rate_limit(exc) is True

    def test_generic_429_substring(self):
        assert detect_rate_limit(RuntimeError("HTTP 429: too many requests")) is True

    def test_azure_503_with_throttle_word(self):
        assert detect_rate_limit(Exception("Service Unavailable: 503 throttle, retry later")) is True

    def test_azure_503_alone_is_not_rate_limit(self):
        # 503 alone is too generic — only treat as rate-limit if the message
        # also mentions throttle/quota/rate.
        assert detect_rate_limit(Exception("Service Unavailable: 503")) is False

    def test_rejects_500(self):
        assert detect_rate_limit(RuntimeError("HTTP 500: server error")) is False

    def test_rejects_value_error(self):
        assert detect_rate_limit(ValueError("bad input")) is False
