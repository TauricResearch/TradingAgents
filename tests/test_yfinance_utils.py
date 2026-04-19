# Copyright 2026 herald.k, HongSoo Kim
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for yfinance retry, backoff, and caching utilities."""

import time
from unittest.mock import patch, MagicMock

import pytest

from tradingagents.dataflows.yfinance_utils import (
    YFRateLimitError,
    TTLCache,
    yfinance_retry,
    yfinance_cached,
    get_yfinance_cache,
)


# ---------------------------------------------------------------------------
# yfinance_retry tests
# ---------------------------------------------------------------------------


@patch("tradingagents.dataflows.yfinance_utils.time.sleep")
@patch("tradingagents.dataflows.config.get_config", return_value={
    "yfinance_retry": {"max_retries": 3, "base_delay": 1.0, "max_delay": 60.0, "backoff_factor": 2.0}
})
def test_retry_succeeds_after_transient_error(mock_config, mock_sleep):
    """Retry should succeed when the function recovers after rate limit errors."""
    call_count = 0

    @yfinance_retry()
    def flaky_func():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise YFRateLimitError()
        return "success"

    result = flaky_func()
    assert result == "success"
    assert call_count == 3
    assert mock_sleep.call_count == 2


@patch("tradingagents.dataflows.yfinance_utils.time.sleep")
@patch("tradingagents.dataflows.config.get_config", return_value={
    "yfinance_retry": {"max_retries": 2, "base_delay": 1.0, "max_delay": 60.0, "backoff_factor": 2.0}
})
def test_retry_raises_after_max_retries(mock_config, mock_sleep):
    """Should re-raise YFRateLimitError after exhausting all retries."""

    @yfinance_retry()
    def always_fails():
        raise YFRateLimitError()

    with pytest.raises(YFRateLimitError):
        always_fails()

    assert mock_sleep.call_count == 2


@patch("tradingagents.dataflows.yfinance_utils.time.sleep")
@patch("tradingagents.dataflows.config.get_config", return_value={
    "yfinance_retry": {"max_retries": 3, "base_delay": 2.0, "max_delay": 60.0, "backoff_factor": 2.0}
})
def test_retry_exponential_backoff(mock_config, mock_sleep):
    """Backoff delays should increase exponentially."""

    @yfinance_retry()
    def always_fails():
        raise YFRateLimitError()

    with pytest.raises(YFRateLimitError):
        always_fails()

    delays = [call.args[0] for call in mock_sleep.call_args_list]
    assert delays == [2.0, 4.0, 8.0]


@patch("tradingagents.dataflows.yfinance_utils.time.sleep")
@patch("tradingagents.dataflows.config.get_config", return_value={})
def test_retry_does_not_catch_other_exceptions(mock_config, mock_sleep):
    """Non-rate-limit exceptions should propagate immediately without retry."""

    @yfinance_retry()
    def raises_value_error():
        raise ValueError("not a rate limit")

    with pytest.raises(ValueError, match="not a rate limit"):
        raises_value_error()

    assert mock_sleep.call_count == 0


# ---------------------------------------------------------------------------
# TTLCache tests
# ---------------------------------------------------------------------------


def test_cache_put_and_get():
    """Cached values should be retrievable before TTL expires."""
    cache = TTLCache(default_ttl_seconds=60)
    cache.put("key1", "value1")
    assert cache.get("key1") == "value1"


def test_cache_expiry():
    """Cached values should expire after TTL."""
    cache = TTLCache(default_ttl_seconds=0)  # Immediate expiry
    cache.put("key1", "value1", ttl_seconds=0)

    # Force expiry by waiting a tiny bit
    time.sleep(0.01)
    assert cache.get("key1") is None


def test_cache_miss():
    """Missing keys should return None."""
    cache = TTLCache()
    assert cache.get("nonexistent") is None


def test_cache_clear():
    """Clear should remove all entries."""
    cache = TTLCache()
    cache.put("k1", "v1")
    cache.put("k2", "v2")
    cache.clear()
    assert cache.get("k1") is None
    assert cache.get("k2") is None


def test_cache_make_key_deterministic():
    """Same args should produce the same cache key."""
    cache = TTLCache()
    key1 = cache.make_key("func", ("AAPL",), {"freq": "quarterly"})
    key2 = cache.make_key("func", ("AAPL",), {"freq": "quarterly"})
    assert key1 == key2


def test_cache_make_key_different_args():
    """Different args should produce different cache keys."""
    cache = TTLCache()
    key1 = cache.make_key("func", ("AAPL",), {})
    key2 = cache.make_key("func", ("MSFT",), {})
    assert key1 != key2


# ---------------------------------------------------------------------------
# yfinance_cached tests
# ---------------------------------------------------------------------------


def test_cached_returns_cached_value():
    """Second call should return cached value without calling the function again."""
    cache = get_yfinance_cache()
    cache.clear()

    call_count = 0

    @yfinance_cached(ttl_seconds=60)
    def expensive_func(ticker):
        nonlocal call_count
        call_count += 1
        return f"data for {ticker}"

    result1 = expensive_func("AAPL")
    result2 = expensive_func("AAPL")

    assert result1 == result2 == "data for AAPL"
    assert call_count == 1  # Only called once

    cache.clear()


def test_cached_does_not_cache_error_strings():
    """Error strings should not be cached."""
    cache = get_yfinance_cache()
    cache.clear()

    call_count = 0

    @yfinance_cached(ttl_seconds=60)
    def failing_func(ticker):
        nonlocal call_count
        call_count += 1
        return f"Error retrieving data for {ticker}"

    result1 = failing_func("AAPL")
    result2 = failing_func("AAPL")

    assert "Error" in result1
    assert call_count == 2  # Called twice, error was not cached

    cache.clear()
