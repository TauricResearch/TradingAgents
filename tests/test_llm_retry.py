"""Unit tests for the LLM retry-with-backoff module."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from openai import APIConnectionError, APITimeoutError, RateLimitError

from tradingagents.llm_clients.retry import (
    RETRYABLE_STATUS_CODES,
    RetryPolicy,
    _compute_delay,
    _is_retryable_by_class,
    _retry_after_seconds,
    _status_code,
    invoke_with_retry,
    is_retryable,
    with_retry,
)


class _FakeResp:
    def __init__(self, code, headers=None):
        self.status_code = code
        self.headers = headers or {}
        self.request = MagicMock()


class _FakeExc(Exception):
    """A minimal stand-in for an SDK exception that has ``status_code`` and
    ``response`` attributes the same way openai / anthropic / google do."""

    def __init__(self, code, headers=None):
        super().__init__(f"fake {code}")
        self.status_code = code
        self.response = _FakeResp(code, headers)


@pytest.mark.unit
class TestIsRetryable:
    def test_429_is_retryable(self):
        assert is_retryable(_FakeExc(429, {"retry-after": "5"})) is True

    def test_500_502_503_504_are_retryable(self):
        for code in (500, 502, 503, 504):
            assert is_retryable(_FakeExc(code)) is True

    @pytest.mark.parametrize("code", [400, 401, 403, 404, 422])
    def test_client_errors_other_than_429_are_not_retryable(self, code):
        # Hitting a 401 mid-graph is a config problem, not a hiccup; retrying
        # would just delay the failure surface.
        assert is_retryable(_FakeExc(code)) is False

    def test_value_error_not_retryable(self):
        assert is_retryable(ValueError("boom")) is False

    def test_openai_rate_limit_error_class_is_retryable(self):
        err = RateLimitError(
            "rate", response=_FakeResp(429, {"retry-after": "1"}), body=None
        )
        assert is_retryable(err) is True

    def test_openai_connection_error_class_is_retryable(self):
        err = APIConnectionError(request=_FakeResp(0).request)
        assert is_retryable(err) is True

    def test_openai_timeout_error_class_is_retryable(self):
        err = APITimeoutError(request=_FakeResp(0).request)
        assert is_retryable(err) is True

    def test_message_string_fallback_for_429(self):
        # Custom gateway or transport that raises plain Exception with
        # 'rate limit' / 'too many requests' in the message.
        assert is_retryable(RuntimeError("rate limit exceeded")) is True
        assert is_retryable(RuntimeError("too many requests, slow down")) is True
        assert is_retryable(RuntimeError("connection timed out")) is True

    def test_status_code_lookup_falls_through_to_response(self):
        class NoStatusCode(Exception):
            def __init__(self, resp):
                super().__init__("x")
                self.response = resp

        err = NoStatusCode(_FakeResp(503))
        assert is_retryable(err) is True

    def test_status_code_helper(self):
        assert _status_code(_FakeExc(429)) == 429
        assert _status_code(ValueError("x")) is None


@pytest.mark.unit
class TestRetryAfter:
    def test_parses_numeric_header(self):
        exc = _FakeExc(429, {"retry-after": "12.5"})
        assert _retry_after_seconds(exc) == 12.5

    def test_returns_none_for_date_form(self):
        # HTTP-date form is not handled — caller falls back to exp backoff.
        exc = _FakeExc(429, {"retry-after": "Wed, 21 Oct 2015 07:28:00 GMT"})
        assert _retry_after_seconds(exc) is None

    def test_returns_none_when_no_header(self):
        assert _retry_after_seconds(_FakeExc(500)) is None

    def test_returns_none_when_no_response(self):
        assert _retry_after_seconds(ValueError("x")) is None


@pytest.mark.unit
class TestRetryableClassNames:
    """The class-name fallback is for SDKs that don't expose
    ``status_code`` (e.g. raw httpx). These pins prevent accidental
    deletions that would break the retry path on those SDKs."""

    def test_httpx_timeout_class_matches(self):
        class Timeout(Exception):
            pass
        assert _is_retryable_by_class(Timeout()) is True

    def test_unrelated_exception_does_not_match(self):
        class Whatever(Exception):
            pass
        assert _is_retryable_by_class(Whatever()) is False


@pytest.mark.unit
class TestComputeDelay:
    def test_exponential_backoff_without_retry_after(self):
        p = RetryPolicy(
            max_retries=5, base_delay_seconds=1.0, max_delay_seconds=60.0, jitter=0.0
        )
        assert _compute_delay(0, p, _FakeExc(500)) == 1.0
        assert _compute_delay(1, p, _FakeExc(500)) == 2.0
        assert _compute_delay(2, p, _FakeExc(500)) == 4.0
        assert _compute_delay(3, p, _FakeExc(500)) == 8.0

    def test_caps_at_max_delay(self):
        p = RetryPolicy(
            max_retries=10, base_delay_seconds=1.0, max_delay_seconds=10.0, jitter=0.0
        )
        # Past attempt 4, 1 * 2**a would exceed 10.
        for a in range(4, 7):
            assert _compute_delay(a, p, _FakeExc(500)) == 10.0

    def test_retry_after_overrides_exponential(self):
        p = RetryPolicy(
            max_retries=5, base_delay_seconds=1.0, max_delay_seconds=60.0, jitter=0.0
        )
        # Server told us 30s; that wins.
        assert _compute_delay(0, p, _FakeExc(429, {"retry-after": "30"})) == 30.0

    def test_retry_after_still_capped(self):
        p = RetryPolicy(
            max_retries=5, base_delay_seconds=1.0, max_delay_seconds=15.0, jitter=0.0
        )
        # Even with Retry-After: 60, we cap at 15.
        assert _compute_delay(0, p, _FakeExc(429, {"retry-after": "60"})) == 15.0

    def test_jitter_spreads_within_bounds(self):
        p = RetryPolicy(
            max_retries=5, base_delay_seconds=2.0, max_delay_seconds=60.0, jitter=0.5
        )
        for _ in range(20):
            d = _compute_delay(1, p, _FakeExc(500))  # base 2 * 2 = 4
            # Range with jitter=0.5: [4 * 0.5, 4 * 1.5] = [2, 6]
            assert 2.0 <= d <= 6.0


@pytest.mark.unit
class TestInvokeWithRetry:
    def test_returns_immediately_on_success(self):
        sleeps = []
        p = RetryPolicy(
            max_retries=3, base_delay_seconds=1.0, sleep=sleeps.append
        )
        result = invoke_with_retry(lambda: "ok", policy=p)
        assert result == "ok"
        assert sleeps == []

    def test_retries_on_429_then_succeeds(self):
        sleeps = []
        p = RetryPolicy(
            max_retries=3, base_delay_seconds=1.0, max_delay_seconds=10.0,
            jitter=0.0, sleep=sleeps.append,
        )
        attempts = {"n": 0}
        def flaky():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise _FakeExc(429, {"retry-after": "2"})
            return "ok"
        assert invoke_with_retry(flaky, policy=p) == "ok"
        assert attempts["n"] == 3
        assert len(sleeps) == 2
        # Retry-After: 2 with jitter=0 is exactly 2s.
        assert sleeps == [2.0, 2.0]

    def test_does_not_retry_non_retryable(self):
        sleeps = []
        p = RetryPolicy(
            max_retries=3, base_delay_seconds=1.0, sleep=sleeps.append
        )
        attempts = {"n": 0}
        def bad():
            attempts["n"] += 1
            raise ValueError("nope")
        with pytest.raises(ValueError):
            invoke_with_retry(bad, policy=p)
        assert attempts["n"] == 1
        assert sleeps == []

    def test_raises_last_exception_on_exhaustion(self):
        sleeps = []
        p = RetryPolicy(
            max_retries=2, base_delay_seconds=0.0, max_delay_seconds=0.0,
            jitter=0.0, sleep=sleeps.append,
        )
        def always_fail():
            raise _FakeExc(429)
        with pytest.raises(_FakeExc):
            invoke_with_retry(always_fail, policy=p)
        # 1 initial attempt + 2 retries = 3 calls
        assert len(sleeps) == 2

    def test_max_retries_zero_means_no_retry(self):
        p = RetryPolicy(max_retries=0, base_delay_seconds=0.0, sleep=lambda s: None)
        attempts = {"n": 0}
        def fail():
            attempts["n"] += 1
            raise _FakeExc(429)
        with pytest.raises(_FakeExc):
            invoke_with_retry(fail, policy=p)
        assert attempts["n"] == 1

    def test_negative_max_retries_raises(self):
        p = RetryPolicy(max_retries=-1, base_delay_seconds=0.0, sleep=lambda s: None)
        with pytest.raises(ValueError):
            invoke_with_retry(lambda: None, policy=p)

    def test_on_retry_callback_fires(self):
        events = []
        p = RetryPolicy(
            max_retries=2, base_delay_seconds=0.0, max_delay_seconds=0.0,
            jitter=0.0, sleep=lambda s: None,
            on_retry=lambda a, d, exc: events.append((a, d, type(exc).__name__)),
        )
        def flaky():
            if len(events) < 2:
                raise _FakeExc(429)
            return "ok"
        assert invoke_with_retry(flaky, policy=p) == "ok"
        assert len(events) == 2
        assert events[0][0] == 0
        assert events[0][2] == "_FakeExc"

    def test_on_retry_callback_that_raises_does_not_break_retry(self):
        """The callback is for observability only — it must not abort the loop."""
        sleeps = []
        p = RetryPolicy(
            max_retries=2, base_delay_seconds=0.0, max_delay_seconds=0.0,
            jitter=0.0, sleep=sleeps.append,
            on_retry=lambda *_: (_ for _ in ()).throw(RuntimeError("callback boom")),
        )
        def flaky():
            if not sleeps:
                raise _FakeExc(429)
            return "ok"
        assert invoke_with_retry(flaky, policy=p) == "ok"


@pytest.mark.unit
class TestWithRetryDecorator:
    def test_decorator_wraps_and_retries(self):
        sleeps = []
        p = RetryPolicy(
            max_retries=2, base_delay_seconds=0.0, max_delay_seconds=0.0,
            jitter=0.0, sleep=sleeps.append,
        )

        attempts = {"n": 0}
        @with_retry(p)
        def flaky():
            attempts["n"] += 1
            if attempts["n"] < 2:
                raise _FakeExc(429)
            return "ok"

        assert flaky() == "ok"
        assert attempts["n"] == 2
        assert len(sleeps) == 1
