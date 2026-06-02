"""Unit tests for web.server.retry — pure-function helpers."""
from __future__ import annotations

import random
from datetime import datetime, timezone

import pytest

from web.server.retry import compute_backoff, detect_rate_limit, parse_retry_after


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


class TestComputeBackoff:
    def test_returns_hint_when_within_cap(self):
        exc = Exception("'retryDelay': '5s'")
        assert compute_backoff(0, exc) == 5.0

    def test_returns_hint_at_cap(self):
        exc = Exception("'retryDelay': '60s'")
        assert compute_backoff(0, exc) == 60.0

    def test_hint_above_cap_falls_back_to_exponential(self):
        # 100s hint exceeds default cap of 60 → falls back.
        # With random.seed(0) on attempt=0, the exponential+jitter is 1.0..1.25.
        exc = Exception("'retryDelay': '100s'")
        random.seed(0)
        result = compute_backoff(0, exc)
        assert 1.0 <= result <= 1.25

    def test_no_hint_returns_exponential_with_jitter(self):
        # attempt=0: base=1, jitter 0..0.25
        random.seed(0)
        assert 1.0 <= compute_backoff(0, Exception("x")) <= 1.25
        # attempt=1: base=2, jitter 0..0.5
        assert 2.0 <= compute_backoff(1, Exception("x")) <= 2.5
        # attempt=2: base=4, jitter 0..1.0
        assert 4.0 <= compute_backoff(2, Exception("x")) <= 5.0
        # attempt=3: base=8, jitter 0..2.0
        assert 8.0 <= compute_backoff(3, Exception("x")) <= 10.0

    def test_caps_at_max_s_for_high_attempt(self):
        # attempt=20 would be 2**20 = 1M, must be capped.
        result = compute_backoff(20, Exception("x"))
        assert 0 < result <= 60.0

    def test_custom_max_s(self):
        # Hint within custom cap → returned as-is.
        exc = Exception("'retryDelay': '5s'")
        assert compute_backoff(0, exc, max_s=10.0) == 5.0
        # Hint above custom cap → fallback.
        random.seed(0)
        result = compute_backoff(0, exc, max_s=2.0)
        assert 0 < result <= 2.0
