"""Unit tests for web.server.retry — pure-function helpers."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from web.server.retry import detect_rate_limit, parse_retry_after


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


class TestParseRetryAfter:
    def test_google_retry_delay_seconds(self):
        exc = Exception("'retryDelay': '46s'")
        assert parse_retry_after(exc) == 46.0

    def test_google_retry_delay_decimal(self):
        exc = Exception("'retryDelay': '46.5s'")
        assert parse_retry_after(exc) == 46.5

    def test_google_retry_delay_milliseconds(self):
        exc = Exception("'retryDelay': '1200ms'")
        assert parse_retry_after(exc) == 1.2

    def test_retry_after_header_seconds(self):
        exc = Exception("HTTP 429: rate limit. Retry-After: 46")
        assert parse_retry_after(exc) == 46.0

    def test_retry_after_header_case_insensitive(self):
        exc = Exception("HTTP 429: rate limit. retry-after: 30")
        assert parse_retry_after(exc) == 30.0

    def test_retry_in_seconds_decimal(self):
        # Don't lose precision on a provider hint; the runner's compute_backoff
        # will clamp to max_s anyway, but parse_retry_after should be honest.
        exc = Exception("Quota exceeded. Please retry in 46.512845114s.")
        result = parse_retry_after(exc)
        assert result is not None
        assert 46.5 <= result <= 46.6

    def test_retry_after_word_seconds(self):
        exc = Exception("Please retry after 30 seconds")
        assert parse_retry_after(exc) == 30.0

    def test_returns_none_for_unparseable(self):
        exc = Exception("Some error without any retry info")
        assert parse_retry_after(exc) is None

    def test_returns_none_for_empty_message(self):
        assert parse_retry_after(Exception("")) is None

    def test_retry_after_http_date_with_fixed_now(self):
        # 2026-06-02T12:00:00Z is the fixed "now" for this test.
        fixed_now = datetime(2026, 6, 2, 12, 0, 0, tzinfo=timezone.utc)
        # Target is 60 seconds after "now".
        exc = Exception("Retry-After: Tue, 02 Jun 2026 12:01:00 GMT")
        result = parse_retry_after(exc, now=fixed_now)
        assert result is not None
        assert 59.0 <= result <= 60.0

    def test_retry_after_http_date_in_past_returns_none(self):
        fixed_now = datetime(2026, 6, 2, 12, 0, 0, tzinfo=timezone.utc)
        exc = Exception("Retry-After: Mon, 01 Jun 2026 12:00:00 GMT")
        assert parse_retry_after(exc, now=fixed_now) is None

    def test_retry_after_huge_seconds_is_clamped_to_none(self):
        # 24h+ hints are treated as "give up" and filtered out so the
        # caller can fall back to exponential backoff.
        exc = Exception("'retryDelay': '100000s'")
        assert parse_retry_after(exc) is None
