"""Tests for yf_retry robustness and retry logic.

Covers the enhanced exponential backoff with jitter, max retry limits,
and proper exception propagation.
"""
from unittest.mock import patch

import pytest
from yfinance.exceptions import YFRateLimitError

from tradingagents.dataflows.stockstats_utils import yf_retry


class TestYfRetry:
    """Unit tests for the yf_retry helper."""

    def test_success_on_first_call(self):
        """If the wrapped function succeeds immediately, return its result."""
        call_count = 0

        def success_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = yf_retry(success_func)
        assert result == "success"
        assert call_count == 1

    def test_retries_on_rate_limit_then_succeeds(self):
        """Retry on YFRateLimitError and return the result when it succeeds."""
        call_count = 0

        def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise YFRateLimitError()
            return "recovered"

        with patch("time.sleep"):
            result = yf_retry(flaky_func, max_retries=5)

        assert result == "recovered"
        assert call_count == 3

    def test_raises_after_max_retries_exceeded(self):
        """Raise the last exception if all retries are exhausted."""

        def always_fails():
            raise YFRateLimitError()

        with pytest.raises(YFRateLimitError):
            yf_retry(always_fails, max_retries=2, base_delay=0.0)

    def test_non_rate_limit_exceptions_propagate_immediately(self):
        """Non-YFRateLimitError exceptions should not trigger retries."""
        call_count = 0

        def raises_value_error():
            nonlocal call_count
            call_count += 1
            raise ValueError("Not a rate limit")

        with pytest.raises(ValueError, match="Not a rate limit"):
            yf_retry(raises_value_error)

        assert call_count == 1

    def test_jitter_is_applied(self):
        """Verify that jitter is added to the delay (non-deterministic but bounded)."""
        delays_seen = []

        def fail():
            raise YFRateLimitError()

        with (
            patch("time.sleep", side_effect=lambda d: delays_seen.append(d)),
            pytest.raises(YFRateLimitError),
        ):
            yf_retry(fail, max_retries=3, base_delay=1.0, max_delay=10.0)

        assert len(delays_seen) == 3  # 3 retries
        # With base_delay=1, max_delay=10:
        #   attempt 0: min(1*2^0, 10) + jitter → [1, 2)
        #   attempt 1: min(1*2^1, 10) + jitter → [2, 3)
        #   attempt 2: min(1*2^2, 10) + jitter → [4, 5)
        assert 1.0 <= delays_seen[0] < 2.0
        assert 2.0 <= delays_seen[1] < 3.0
        assert 4.0 <= delays_seen[2] < 5.0

    def test_delay_capped_at_max_delay(self):
        """When backoff exceeds max_delay, it should be capped."""
        delays_seen = []

        def fail():
            raise YFRateLimitError()

        with (
            patch("time.sleep", side_effect=lambda d: delays_seen.append(d)),
            pytest.raises(YFRateLimitError),
        ):
            yf_retry(fail, max_retries=10, base_delay=2.0, max_delay=5.0)

        # After a few doublings, delay should be capped at 5.0 + jitter
        for d in delays_seen[2:]:  # Check the later retries which should be capped
            assert d <= 6.0  # max_delay + 1.0 (max jitter)

    def test_zero_retries(self):
        """With max_retries=0, should not retry at all."""
        call_count = 0

        def fail():
            nonlocal call_count
            call_count += 1
            raise YFRateLimitError()

        with pytest.raises(YFRateLimitError):
            yf_retry(fail, max_retries=0)

        assert call_count == 1

    def test_logs_on_retry(self, caplog):
        """Verify that retry attempts generate warning logs."""
        call_state = {"count": 0}

        def fail_once():
            call_state["count"] += 1
            if call_state["count"] == 1:
                raise YFRateLimitError()
            return "ok"

        with patch("time.sleep"):
            yf_retry(fail_once, max_retries=2)

        assert "Yahoo Finance rate limited" in caplog.text
        assert "attempt 1/2" in caplog.text

    def test_logs_error_after_max_retries(self, caplog):
        """Verify that exhaustion of retries generates an error log."""

        def always_fail():
            raise YFRateLimitError()

        with patch("time.sleep"), pytest.raises(YFRateLimitError):
            yf_retry(always_fail, max_retries=1)

        assert "persisted after 1 retries" in caplog.text
