"""Decorators for vendor registration and method management.

Provides convenient decorators for registering vendors and methods with
the global registry.

Issue #11: [DATA-10] Interface routing - add new data vendors
"""

from functools import wraps
from typing import Callable, Optional, Set, Type
import threading
import time
import logging

from .vendor_registry import (
    VendorCapability,
    VendorMetadata,
    VendorRegistry,
    get_registry
)

logger = logging.getLogger(__name__)


def register_vendor(
    name: str,
    priority: int = 100,
    capabilities: Optional[Set[VendorCapability]] = None,
    rate_limit_exception: Optional[Type[Exception]] = None,
    description: str = ""
) -> Callable:
    """Class decorator to register a vendor with the global registry.

    Example:
        @register_vendor(
            name="yfinance",
            priority=10,
            capabilities={VendorCapability.STOCK_DATA, VendorCapability.FUNDAMENTALS}
        )
        class YFinanceVendor(BaseVendor):
            pass
    """
    def decorator(cls: Type) -> Type:
        metadata = VendorMetadata(
            name=name,
            priority=priority,
            capabilities=capabilities or set(),
            rate_limit_exception=rate_limit_exception,
            description=description
        )

        # Register vendor on class definition
        get_registry().register_vendor(metadata)

        # Store metadata on class for reference
        cls._vendor_metadata = metadata
        cls._vendor_name = name

        return cls

    return decorator


def vendor_method(
    method_name: str,
    vendor_name: Optional[str] = None
) -> Callable:
    """Decorator to register a method with the vendor registry.

    Can be used as a method decorator on vendor classes or as a
    standalone function decorator.

    Example (on class method):
        class YFinanceVendor(BaseVendor):
            @vendor_method("get_stock_data")
            def get_stock(self, ticker):
                pass

    Example (standalone):
        @vendor_method("get_stock_data", vendor_name="yfinance")
        def get_yfinance_stock(ticker):
            pass
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        # Store registration info for lazy registration
        wrapper._vendor_method_name = method_name
        wrapper._vendor_name = vendor_name

        # If vendor_name provided, register immediately
        if vendor_name:
            try:
                get_registry().register_method(vendor_name, method_name, wrapper)
            except ValueError:
                # Vendor not yet registered - will be registered later
                logger.debug(
                    f"Deferred registration of {method_name} for {vendor_name}"
                )

        return wrapper

    return decorator


class RateLimiter:
    """Thread-safe rate limiter with sliding window.

    Tracks request timestamps and enforces rate limits using a sliding window.
    """

    def __init__(self, max_calls: int, period_seconds: float):
        """Initialize rate limiter.

        Args:
            max_calls: Maximum calls allowed in the period
            period_seconds: Time window in seconds
        """
        self._max_calls = max_calls
        self._period = period_seconds
        self._calls: list = []
        self._lock = threading.Lock()

    def acquire(self) -> bool:
        """Try to acquire a rate limit slot.

        Returns:
            True if request is allowed, False if rate limited
        """
        with self._lock:
            now = time.time()
            cutoff = now - self._period

            # Remove expired entries
            self._calls = [t for t in self._calls if t > cutoff]

            # Check if under limit
            if len(self._calls) < self._max_calls:
                self._calls.append(now)
                return True

            return False

    def wait_time(self) -> float:
        """Get time to wait before next allowed request.

        Returns:
            Seconds to wait (0 if request can proceed)
        """
        with self._lock:
            now = time.time()
            cutoff = now - self._period

            # Remove expired entries
            self._calls = [t for t in self._calls if t > cutoff]

            if len(self._calls) < self._max_calls:
                return 0.0

            # Time until oldest call expires
            return self._calls[0] + self._period - now

    def reset(self) -> None:
        """Reset the rate limiter."""
        with self._lock:
            self._calls.clear()


# Global rate limiters for vendors
_rate_limiters: dict = {}
_rate_limiter_lock = threading.Lock()


def get_rate_limiter(
    vendor_name: str,
    max_calls: int,
    period_seconds: float
) -> RateLimiter:
    """Get or create a rate limiter for a vendor.

    Args:
        vendor_name: Vendor identifier
        max_calls: Max calls per period
        period_seconds: Rate limit period

    Returns:
        RateLimiter instance
    """
    with _rate_limiter_lock:
        key = f"{vendor_name}:{max_calls}:{period_seconds}"
        if key not in _rate_limiters:
            _rate_limiters[key] = RateLimiter(max_calls, period_seconds)
        return _rate_limiters[key]


def rate_limited(
    max_calls: int,
    period_seconds: float = 60.0,
    vendor_name: Optional[str] = None,
    exception_class: Optional[Type[Exception]] = None
) -> Callable:
    """Decorator to apply rate limiting to a function.

    Example:
        @rate_limited(max_calls=5, period_seconds=60, vendor_name="alpha_vantage")
        def get_stock_data(ticker):
            pass
    """
    def decorator(func: Callable) -> Callable:
        # Determine vendor name from function or provided value
        limiter_name = vendor_name or getattr(func, '_vendor_name', func.__name__)

        @wraps(func)
        def wrapper(*args, **kwargs):
            limiter = get_rate_limiter(limiter_name, max_calls, period_seconds)

            if not limiter.acquire():
                wait_seconds = limiter.wait_time()
                error_msg = (
                    f"Rate limit exceeded for {limiter_name}. "
                    f"Try again in {wait_seconds:.1f} seconds"
                )

                if exception_class:
                    raise exception_class(error_msg)
                raise RuntimeError(error_msg)

            return func(*args, **kwargs)

        return wrapper

    return decorator


def with_retry(
    max_retries: int = 3,
    retry_delay: float = 1.0,
    backoff_multiplier: float = 2.0,
    retryable_exceptions: tuple = (ConnectionError, TimeoutError)
) -> Callable:
    """Decorator to add retry logic to a function.

    Example:
        @with_retry(max_retries=3, retry_delay=1.0)
        def fetch_data():
            pass
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            delay = retry_delay

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        logger.warning(
                            f"Retry {attempt + 1}/{max_retries} for {func.__name__}: {e}"
                        )
                        time.sleep(delay)
                        delay *= backoff_multiplier
                    else:
                        raise

            raise last_exception  # type: ignore

        return wrapper

    return decorator


def cache_result(
    ttl_seconds: float = 300.0,
    max_size: int = 100
) -> Callable:
    """Decorator to cache function results.

    Simple TTL-based cache with LRU eviction.

    Example:
        @cache_result(ttl_seconds=60)
        def get_stock_data(ticker):
            pass
    """
    def decorator(func: Callable) -> Callable:
        cache: dict = {}
        cache_lock = threading.Lock()
        access_order: list = []

        @wraps(func)
        def wrapper(*args, **kwargs):
            # Create cache key from args
            key = (args, tuple(sorted(kwargs.items())))
            now = time.time()

            with cache_lock:
                # Check cache
                if key in cache:
                    value, timestamp = cache[key]
                    if now - timestamp < ttl_seconds:
                        # Update access order
                        if key in access_order:
                            access_order.remove(key)
                        access_order.append(key)
                        return value
                    else:
                        # Expired
                        del cache[key]
                        if key in access_order:
                            access_order.remove(key)

            # Execute function
            result = func(*args, **kwargs)

            with cache_lock:
                # Evict oldest if at capacity
                while len(cache) >= max_size and access_order:
                    oldest_key = access_order.pop(0)
                    cache.pop(oldest_key, None)

                # Store result
                cache[key] = (result, now)
                access_order.append(key)

            return result

        # Add cache control methods
        def clear_cache():
            with cache_lock:
                cache.clear()
                access_order.clear()

        def cache_info():
            with cache_lock:
                return {
                    "size": len(cache),
                    "max_size": max_size,
                    "ttl_seconds": ttl_seconds
                }

        wrapper.clear_cache = clear_cache
        wrapper.cache_info = cache_info

        return wrapper

    return decorator
