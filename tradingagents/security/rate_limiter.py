"""
Rate limiting utilities to prevent API quota exhaustion.
"""

import time
from collections import deque
from functools import wraps
from typing import Callable, Optional
import threading


class RateLimiter:
    """
    Thread-safe rate limiter for API calls.

    Examples:
        >>> limiter = RateLimiter(max_calls=60, period=60)
        >>> @limiter
        ... def api_call():
        ...     return "result"
        >>> result = api_call()
    """

    def __init__(self, max_calls: int, period: float, burst: Optional[int] = None):
        """
        Initialize rate limiter.

        Args:
            max_calls: Maximum number of calls allowed in the period
            period: Time period in seconds
            burst: Maximum burst size (default: max_calls)
        """
        self.max_calls = max_calls
        self.period = period
        self.burst = burst or max_calls
        self.calls = deque()
        self.lock = threading.Lock()

    def __call__(self, func: Callable) -> Callable:
        """
        Decorator to rate limit a function.

        Args:
            func: Function to rate limit

        Returns:
            Wrapped function with rate limiting
        """
        @wraps(func)
        def wrapper(*args, **kwargs):
            self._wait_if_needed()
            return func(*args, **kwargs)

        return wrapper

    def _wait_if_needed(self):
        """Wait if rate limit would be exceeded."""
        with self.lock:
            now = time.time()

            # Remove calls outside the time window
            while self.calls and self.calls[0] < now - self.period:
                self.calls.popleft()

            # Check if we need to wait
            if len(self.calls) >= self.max_calls:
                sleep_time = self.period - (now - self.calls[0])
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    # Remove the oldest call after waiting
                    self.calls.popleft()

            # Record this call
            self.calls.append(time.time())

    def reset(self):
        """Reset the rate limiter."""
        with self.lock:
            self.calls.clear()

    def get_stats(self) -> dict:
        """
        Get rate limiter statistics.

        Returns:
            Dictionary with current statistics
        """
        with self.lock:
            now = time.time()

            # Remove old calls
            while self.calls and self.calls[0] < now - self.period:
                self.calls.popleft()

            return {
                'current_calls': len(self.calls),
                'max_calls': self.max_calls,
                'period': self.period,
                'remaining': max(0, self.max_calls - len(self.calls)),
                'reset_in': self.period - (now - self.calls[0]) if self.calls else 0
            }


class MultiTierRateLimiter:
    """
    Multi-tier rate limiter for APIs with multiple rate limits.

    Examples:
        >>> limiter = MultiTierRateLimiter([
        ...     (5, 1),      # 5 calls per second
        ...     (100, 60),   # 100 calls per minute
        ...     (1000, 3600) # 1000 calls per hour
        ... ])
    """

    def __init__(self, limits: list):
        """
        Initialize multi-tier rate limiter.

        Args:
            limits: List of (max_calls, period) tuples
        """
        self.limiters = [
            RateLimiter(max_calls, period)
            for max_calls, period in limits
        ]

    def __call__(self, func: Callable) -> Callable:
        """
        Decorator to apply multi-tier rate limiting.

        Args:
            func: Function to rate limit

        Returns:
            Wrapped function with rate limiting
        """
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Wait for all rate limiters
            for limiter in self.limiters:
                limiter._wait_if_needed()

            return func(*args, **kwargs)

        return wrapper

    def reset(self):
        """Reset all rate limiters."""
        for limiter in self.limiters:
            limiter.reset()

    def get_stats(self) -> list:
        """
        Get statistics for all rate limiters.

        Returns:
            List of statistics dictionaries
        """
        return [limiter.get_stats() for limiter in self.limiters]
