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

"""Retry, backoff, and caching utilities for yfinance API calls."""

import functools
import hashlib
import json
import logging
import time
from datetime import datetime, timedelta
from threading import Lock

try:
    from yfinance.exceptions import YFRateLimitError
except ImportError:

    class YFRateLimitError(Exception):
        """Fallback for older yfinance versions without this exception."""

        pass


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Retry decorator with exponential backoff
# ---------------------------------------------------------------------------


def yfinance_retry(max_retries=None, base_delay=None, max_delay=None, backoff_factor=None):
    """Decorator that retries on YFRateLimitError with exponential backoff.

    If parameters are None, reads from config["yfinance_retry"].
    Falls back to hardcoded defaults if config is unavailable.
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            from .config import get_config

            config = get_config()
            retry_config = config.get("yfinance_retry", {})

            _max_retries = (
                max_retries if max_retries is not None else retry_config.get("max_retries", 3)
            )
            _base_delay = (
                base_delay if base_delay is not None else retry_config.get("base_delay", 2.0)
            )
            _max_delay = (
                max_delay if max_delay is not None else retry_config.get("max_delay", 60.0)
            )
            _backoff_factor = (
                backoff_factor
                if backoff_factor is not None
                else retry_config.get("backoff_factor", 2.0)
            )

            delay = _base_delay
            last_exception = None
            for attempt in range(_max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except YFRateLimitError as e:
                    last_exception = e
                    if attempt < _max_retries:
                        sleep_time = min(delay, _max_delay)
                        logger.warning(
                            "YFinance rate limited on %s (attempt %d/%d). "
                            "Retrying in %.1fs...",
                            func.__name__,
                            attempt + 1,
                            _max_retries,
                            sleep_time,
                        )
                        time.sleep(sleep_time)
                        delay *= _backoff_factor
                    else:
                        logger.error(
                            "YFinance rate limited on %s after %d retries. Giving up.",
                            func.__name__,
                            _max_retries,
                        )
            raise last_exception

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# TTL in-memory cache
# ---------------------------------------------------------------------------


class TTLCache:
    """Simple thread-safe in-memory cache with per-entry TTL expiration."""

    def __init__(self, default_ttl_seconds=3600):
        self._store = {}  # key -> (value, expiry_datetime)
        self._lock = Lock()
        self.default_ttl = default_ttl_seconds

    def make_key(self, func_name: str, args: tuple, kwargs: dict) -> str:
        """Create a deterministic cache key from function name and arguments."""
        key_data = json.dumps(
            {"fn": func_name, "args": list(args), "kwargs": kwargs},
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(key_data.encode()).hexdigest()

    def get(self, key: str):
        """Return cached value or None if missing/expired."""
        with self._lock:
            if key in self._store:
                value, expiry = self._store[key]
                if datetime.now() < expiry:
                    return value
                del self._store[key]
        return None

    def put(self, key: str, value, ttl_seconds: int = None):
        """Store a value with TTL."""
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl
        with self._lock:
            self._store[key] = (value, datetime.now() + timedelta(seconds=ttl))

    def clear(self):
        """Clear all cached entries."""
        with self._lock:
            self._store.clear()


# Module-level singleton cache instance
_yfinance_cache = TTLCache()


def get_yfinance_cache() -> TTLCache:
    """Get the module-level yfinance cache singleton."""
    return _yfinance_cache


def yfinance_cached(ttl_seconds=None):
    """Decorator that caches function results with TTL.

    Args:
        ttl_seconds: Cache TTL in seconds. If None, uses the cache default.
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            cache = get_yfinance_cache()
            key = cache.make_key(func.__name__, args, kwargs)
            cached = cache.get(key)
            if cached is not None:
                logger.debug("Cache hit for %s", func.__name__)
                return cached
            result = func(*args, **kwargs)
            # Only cache successful results (not error strings)
            if not isinstance(result, str) or not result.startswith("Error"):
                cache.put(key, result, ttl_seconds)
            return result

        return wrapper

    return decorator
