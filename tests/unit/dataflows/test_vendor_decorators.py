"""Tests for vendor decorators.

Issue #11: [DATA-10] Interface routing - add new data vendors
"""

import pytest
import time
import threading
from unittest.mock import Mock

from tradingagents.dataflows.vendor_registry import (
    VendorCapability,
    VendorMetadata,
    VendorRegistry,
)
from tradingagents.dataflows.vendor_decorators import (
    register_vendor,
    vendor_method,
    rate_limited,
    with_retry,
    cache_result,
    RateLimiter,
    get_rate_limiter,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def reset_registry():
    """Reset the singleton registry before each test."""
    VendorRegistry.reset_instance()
    yield
    VendorRegistry.reset_instance()


class TestRegisterVendorDecorator:
    """Tests for @register_vendor decorator."""

    def test_register_vendor_basic(self):
        """Test basic vendor registration with decorator."""
        @register_vendor(
            name="test_vendor",
            capabilities={VendorCapability.STOCK_DATA},
            priority=10
        )
        class TestVendor:
            pass

        assert hasattr(TestVendor, '_vendor_metadata')
        assert TestVendor._vendor_name == "test_vendor"

    def test_register_vendor_adds_to_registry(self):
        """Test that decorator adds vendor to registry."""
        @register_vendor(
            name="registered_vendor",
            capabilities={VendorCapability.STOCK_DATA}
        )
        class RegisteredVendor:
            pass

        registry = VendorRegistry()
        assert registry.get_vendor("registered_vendor") is not None

    def test_register_vendor_with_multiple_capabilities(self):
        """Test registering vendor with multiple capabilities."""
        @register_vendor(
            name="multi_vendor",
            capabilities={
                VendorCapability.STOCK_DATA,
                VendorCapability.FUNDAMENTALS,
                VendorCapability.NEWS
            }
        )
        class MultiVendor:
            pass

        registry = VendorRegistry()
        vendor = registry.get_vendor("multi_vendor")
        assert len(vendor.capabilities) == 3

    def test_register_vendor_preserves_class_methods(self):
        """Test that decorator preserves class methods."""
        @register_vendor(
            name="method_vendor",
            capabilities={VendorCapability.STOCK_DATA}
        )
        class MethodVendor:
            def fetch_data(self):
                return "data"

        vendor = MethodVendor()
        assert vendor.fetch_data() == "data"


class TestVendorMethodDecorator:
    """Tests for @vendor_method decorator."""

    def test_vendor_method_basic(self):
        """Test basic method mapping."""
        class TestVendor:
            @vendor_method("get_stock_data")
            def fetch_stock(self, ticker):
                return f"Stock: {ticker}"

        vendor = TestVendor()
        result = vendor.fetch_stock("AAPL")

        assert result == "Stock: AAPL"
        assert vendor.fetch_stock._vendor_method_name == "get_stock_data"

    def test_vendor_method_with_vendor_name(self):
        """Test vendor_method with explicit vendor name."""
        # Register the vendor first
        registry = VendorRegistry()
        registry.register_vendor(VendorMetadata(name="yfinance"))

        @vendor_method("get_stock", vendor_name="yfinance")
        def get_yfinance_stock(ticker):
            return f"YF: {ticker}"

        # Method should be registered
        method = registry.get_method("yfinance", "get_stock")
        assert method is not None

    def test_vendor_method_preserves_function(self):
        """Test that decorator preserves function behavior."""
        class TestVendor:
            @vendor_method("get_data")
            def fetch_data(self, ticker, start_date=None):
                return {"ticker": ticker, "start": start_date}

        vendor = TestVendor()
        result = vendor.fetch_data("AAPL", start_date="2024-01-01")

        assert result["ticker"] == "AAPL"
        assert result["start"] == "2024-01-01"


class TestRateLimiter:
    """Tests for RateLimiter class."""

    def test_rate_limiter_allows_calls_under_limit(self):
        """Test that calls under limit are allowed."""
        limiter = RateLimiter(max_calls=5, period_seconds=60)

        for _ in range(5):
            assert limiter.acquire() is True

    def test_rate_limiter_blocks_over_limit(self):
        """Test that calls over limit are blocked."""
        limiter = RateLimiter(max_calls=3, period_seconds=60)

        # Use all slots
        for _ in range(3):
            limiter.acquire()

        # 4th call should be blocked
        assert limiter.acquire() is False

    def test_rate_limiter_wait_time(self):
        """Test wait_time calculation."""
        limiter = RateLimiter(max_calls=2, period_seconds=60)

        # Fill up the slots
        limiter.acquire()
        limiter.acquire()

        # Should have positive wait time
        wait = limiter.wait_time()
        assert wait > 0
        assert wait <= 60

    def test_rate_limiter_reset(self):
        """Test reset clears the limiter."""
        limiter = RateLimiter(max_calls=2, period_seconds=60)

        limiter.acquire()
        limiter.acquire()
        assert limiter.acquire() is False

        limiter.reset()
        assert limiter.acquire() is True


class TestRateLimitedDecorator:
    """Tests for @rate_limited decorator."""

    def test_rate_limited_allows_calls_under_limit(self):
        """Test that calls under limit succeed."""
        call_count = [0]

        @rate_limited(max_calls=5, period_seconds=60)
        def limited_func():
            call_count[0] += 1
            return "success"

        for _ in range(5):
            result = limited_func()
            assert result == "success"

        assert call_count[0] == 5

    def test_rate_limited_blocks_over_limit(self):
        """Test that calls over limit raise error."""
        @rate_limited(max_calls=2, period_seconds=60)
        def limited_func():
            return "success"

        limited_func()
        limited_func()

        with pytest.raises(RuntimeError, match="Rate limit exceeded"):
            limited_func()

    def test_rate_limited_custom_exception(self):
        """Test rate limiting with custom exception class."""
        class CustomRateLimitError(Exception):
            pass

        @rate_limited(
            max_calls=1,
            period_seconds=60,
            exception_class=CustomRateLimitError
        )
        def limited_func():
            return "success"

        limited_func()

        with pytest.raises(CustomRateLimitError):
            limited_func()


class TestWithRetryDecorator:
    """Tests for @with_retry decorator."""

    def test_retry_on_retryable_error(self):
        """Test retry on retryable exceptions."""
        attempt_count = [0]

        @with_retry(max_retries=3, retry_delay=0.01)
        def failing_func():
            attempt_count[0] += 1
            if attempt_count[0] < 3:
                raise ConnectionError("Network error")
            return "success"

        result = failing_func()
        assert result == "success"
        assert attempt_count[0] == 3

    def test_no_retry_on_non_retryable_error(self):
        """Test no retry on non-retryable exceptions."""
        attempt_count = [0]

        @with_retry(
            max_retries=3,
            retry_delay=0.01,
            retryable_exceptions=(ConnectionError,)
        )
        def failing_func():
            attempt_count[0] += 1
            raise ValueError("Not retryable")

        with pytest.raises(ValueError):
            failing_func()

        assert attempt_count[0] == 1

    def test_retry_exhausted(self):
        """Test exception raised after max retries."""
        @with_retry(max_retries=2, retry_delay=0.01)
        def always_fails():
            raise ConnectionError("Always fails")

        with pytest.raises(ConnectionError):
            always_fails()


class TestCacheResultDecorator:
    """Tests for @cache_result decorator."""

    def test_cache_returns_cached_value(self):
        """Test that cached value is returned."""
        call_count = [0]

        @cache_result(ttl_seconds=300)
        def expensive_func(key):
            call_count[0] += 1
            return f"value_{key}"

        # First call
        result1 = expensive_func("test")
        # Second call (should use cache)
        result2 = expensive_func("test")

        assert result1 == result2
        assert call_count[0] == 1

    def test_cache_different_keys(self):
        """Test that different keys have different cache entries."""
        call_count = [0]

        @cache_result(ttl_seconds=300)
        def expensive_func(key):
            call_count[0] += 1
            return f"value_{key}"

        result1 = expensive_func("key1")
        result2 = expensive_func("key2")

        assert result1 != result2
        assert call_count[0] == 2

    def test_cache_clear(self):
        """Test clearing the cache."""
        call_count = [0]

        @cache_result(ttl_seconds=300)
        def expensive_func(key):
            call_count[0] += 1
            return f"value_{key}"

        expensive_func("test")
        expensive_func.clear_cache()
        expensive_func("test")

        assert call_count[0] == 2

    def test_cache_info(self):
        """Test cache info method."""
        @cache_result(ttl_seconds=60, max_size=100)
        def cached_func(key):
            return key

        cached_func("test1")
        cached_func("test2")

        info = cached_func.cache_info()
        assert info["size"] == 2
        assert info["max_size"] == 100
        assert info["ttl_seconds"] == 60


class TestDecoratorStacking:
    """Tests for stacking multiple decorators."""

    def test_register_and_method_decorators(self):
        """Test stacking @register_vendor and @vendor_method."""
        @register_vendor(
            name="stacked_vendor",
            capabilities={VendorCapability.STOCK_DATA}
        )
        class StackedVendor:
            @vendor_method("get_stock_data")
            def fetch_stock(self, ticker):
                return f"Stock: {ticker}"

        vendor = StackedVendor()

        # Vendor should be registered
        registry = VendorRegistry()
        assert registry.get_vendor("stacked_vendor") is not None

        # Method should work
        result = vendor.fetch_stock("AAPL")
        assert result == "Stock: AAPL"

    def test_method_with_rate_limit(self):
        """Test stacking @vendor_method with @rate_limited."""
        call_count = [0]

        class TestVendor:
            @vendor_method("get_data")
            @rate_limited(max_calls=3, period_seconds=60)
            def fetch_data(self):
                call_count[0] += 1
                return "data"

        vendor = TestVendor()

        # Should work 3 times
        for _ in range(3):
            vendor.fetch_data()

        # 4th should fail
        with pytest.raises(RuntimeError):
            vendor.fetch_data()

        assert call_count[0] == 3


class TestGetRateLimiter:
    """Tests for get_rate_limiter function."""

    def test_returns_same_limiter_for_same_params(self):
        """Test that same params return same limiter."""
        limiter1 = get_rate_limiter("vendor", 5, 60)
        limiter2 = get_rate_limiter("vendor", 5, 60)

        assert limiter1 is limiter2

    def test_returns_different_limiter_for_different_vendor(self):
        """Test that different vendors get different limiters."""
        limiter1 = get_rate_limiter("vendor1", 5, 60)
        limiter2 = get_rate_limiter("vendor2", 5, 60)

        assert limiter1 is not limiter2

    def test_returns_different_limiter_for_different_params(self):
        """Test that different params get different limiters."""
        limiter1 = get_rate_limiter("vendor", 5, 60)
        limiter2 = get_rate_limiter("vendor", 10, 60)

        assert limiter1 is not limiter2
