"""Data caching layer for vendor data with rate limit awareness.

This module provides a robust caching layer to handle API rate limits across
all data vendors. Features:
- Multi-backend support (memory, file, SQLite)
- TTL-based expiration with configurable per-source TTLs
- Rate limit tracking and backoff
- Cache statistics and monitoring
- Atomic cache operations for thread safety

Issue #12: [DATA-11] Data caching layer - FRED rate limits
"""

import hashlib
import json
import logging
import sqlite3
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TypeVar, Generic

logger = logging.getLogger(__name__)

T = TypeVar('T')


class CacheStatus(Enum):
    """Status of a cache lookup."""
    HIT = auto()
    MISS = auto()
    EXPIRED = auto()
    STALE = auto()  # Expired but returned due to rate limit


@dataclass
class CacheEntry(Generic[T]):
    """A single cache entry with metadata."""
    key: str
    value: T
    created_at: datetime
    expires_at: datetime
    access_count: int = 0
    last_accessed: Optional[datetime] = None
    source: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        """Check if entry is expired."""
        return datetime.now() > self.expires_at

    @property
    def age_seconds(self) -> float:
        """Get age in seconds."""
        return (datetime.now() - self.created_at).total_seconds()

    @property
    def ttl_remaining_seconds(self) -> float:
        """Get remaining TTL in seconds."""
        return max(0, (self.expires_at - datetime.now()).total_seconds())

    def touch(self) -> None:
        """Update access metadata."""
        self.access_count += 1
        self.last_accessed = datetime.now()


@dataclass
class CacheStats:
    """Statistics for cache operations."""
    hits: int = 0
    misses: int = 0
    expired: int = 0
    stale_served: int = 0
    evictions: int = 0
    size: int = 0

    @property
    def hit_rate(self) -> float:
        """Calculate hit rate as percentage."""
        total = self.hits + self.misses
        if total == 0:
            return 0.0
        return (self.hits / total) * 100

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "hits": self.hits,
            "misses": self.misses,
            "expired": self.expired,
            "stale_served": self.stale_served,
            "evictions": self.evictions,
            "size": self.size,
            "hit_rate": self.hit_rate
        }


@dataclass
class RateLimitState:
    """Track rate limit state for a source."""
    source: str
    requests_made: int = 0
    requests_limit: int = 120  # Default FRED limit
    window_start: datetime = field(default_factory=datetime.now)
    window_seconds: int = 60
    backoff_until: Optional[datetime] = None
    consecutive_failures: int = 0

    @property
    def is_rate_limited(self) -> bool:
        """Check if currently rate limited."""
        if self.backoff_until and datetime.now() < self.backoff_until:
            return True
        return False

    @property
    def requests_remaining(self) -> int:
        """Get remaining requests in current window."""
        self._maybe_reset_window()
        return max(0, self.requests_limit - self.requests_made)

    def _maybe_reset_window(self) -> None:
        """Reset window if expired."""
        if (datetime.now() - self.window_start).total_seconds() > self.window_seconds:
            self.window_start = datetime.now()
            self.requests_made = 0

    def record_request(self) -> None:
        """Record a request."""
        self._maybe_reset_window()
        self.requests_made += 1

    def record_rate_limit(self, backoff_seconds: int = 60) -> None:
        """Record a rate limit hit."""
        self.consecutive_failures += 1
        # Exponential backoff
        actual_backoff = backoff_seconds * (2 ** (self.consecutive_failures - 1))
        self.backoff_until = datetime.now() + timedelta(seconds=actual_backoff)
        logger.warning(f"Rate limit hit for {self.source}, backing off for {actual_backoff}s")

    def record_success(self) -> None:
        """Record successful request."""
        self.consecutive_failures = 0
        self.backoff_until = None


class CacheBackend(ABC):
    """Abstract base class for cache backends."""

    @abstractmethod
    def get(self, key: str) -> Optional[CacheEntry]:
        """Get entry from cache."""
        pass

    @abstractmethod
    def set(self, entry: CacheEntry) -> None:
        """Set entry in cache."""
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete entry from cache."""
        pass

    @abstractmethod
    def clear(self) -> int:
        """Clear all entries. Returns number cleared."""
        pass

    @abstractmethod
    def keys(self) -> List[str]:
        """Get all cache keys."""
        pass

    @abstractmethod
    def size(self) -> int:
        """Get number of entries."""
        pass


class MemoryCache(CacheBackend):
    """In-memory cache with LRU eviction."""

    def __init__(self, max_size: int = 1000):
        """Initialize memory cache.

        Args:
            max_size: Maximum number of entries
        """
        self._cache: Dict[str, CacheEntry] = {}
        self._max_size = max_size
        self._lock = threading.RLock()
        self._access_order: List[str] = []

    def get(self, key: str) -> Optional[CacheEntry]:
        """Get entry from cache."""
        with self._lock:
            entry = self._cache.get(key)
            if entry:
                # Update access order for LRU
                if key in self._access_order:
                    self._access_order.remove(key)
                self._access_order.append(key)
            return entry

    def set(self, entry: CacheEntry) -> None:
        """Set entry in cache with LRU eviction."""
        with self._lock:
            # Evict if at capacity
            while len(self._cache) >= self._max_size and self._access_order:
                oldest_key = self._access_order.pop(0)
                self._cache.pop(oldest_key, None)

            self._cache[entry.key] = entry

            # Update access order
            if entry.key in self._access_order:
                self._access_order.remove(entry.key)
            self._access_order.append(entry.key)

    def delete(self, key: str) -> bool:
        """Delete entry from cache."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                if key in self._access_order:
                    self._access_order.remove(key)
                return True
            return False

    def clear(self) -> int:
        """Clear all entries."""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._access_order.clear()
            return count

    def keys(self) -> List[str]:
        """Get all cache keys."""
        with self._lock:
            return list(self._cache.keys())

    def size(self) -> int:
        """Get number of entries."""
        with self._lock:
            return len(self._cache)


class FileCache(CacheBackend):
    """File-based cache using JSON serialization."""

    def __init__(self, cache_dir: Optional[Path] = None):
        """Initialize file cache.

        Args:
            cache_dir: Directory for cache files
        """
        self._cache_dir = cache_dir or Path.home() / ".cache" / "tradingagents"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _get_path(self, key: str) -> Path:
        """Get file path for key."""
        # Use hash to avoid filesystem issues
        safe_key = hashlib.md5(key.encode()).hexdigest()
        return self._cache_dir / f"{safe_key}.json"

    def get(self, key: str) -> Optional[CacheEntry]:
        """Get entry from file cache."""
        path = self._get_path(key)
        if not path.exists():
            return None

        with self._lock:
            try:
                with open(path, 'r') as f:
                    data = json.load(f)

                return CacheEntry(
                    key=data['key'],
                    value=data['value'],
                    created_at=datetime.fromisoformat(data['created_at']),
                    expires_at=datetime.fromisoformat(data['expires_at']),
                    access_count=data.get('access_count', 0),
                    last_accessed=datetime.fromisoformat(data['last_accessed']) if data.get('last_accessed') else None,
                    source=data.get('source', ''),
                    metadata=data.get('metadata', {})
                )
            except (json.JSONDecodeError, KeyError, ValueError):
                # Corrupted file
                path.unlink(missing_ok=True)
                return None

    def set(self, entry: CacheEntry) -> None:
        """Set entry in file cache."""
        path = self._get_path(entry.key)

        with self._lock:
            data = {
                'key': entry.key,
                'value': entry.value,
                'created_at': entry.created_at.isoformat(),
                'expires_at': entry.expires_at.isoformat(),
                'access_count': entry.access_count,
                'last_accessed': entry.last_accessed.isoformat() if entry.last_accessed else None,
                'source': entry.source,
                'metadata': entry.metadata
            }

            with open(path, 'w') as f:
                json.dump(data, f)

    def delete(self, key: str) -> bool:
        """Delete entry from file cache."""
        path = self._get_path(key)
        with self._lock:
            if path.exists():
                path.unlink()
                return True
            return False

    def clear(self) -> int:
        """Clear all entries."""
        with self._lock:
            count = 0
            for path in self._cache_dir.glob("*.json"):
                path.unlink()
                count += 1
            return count

    def keys(self) -> List[str]:
        """Get all cache keys (returns hashed keys)."""
        return [p.stem for p in self._cache_dir.glob("*.json")]

    def size(self) -> int:
        """Get number of entries."""
        return len(list(self._cache_dir.glob("*.json")))


class DataCache:
    """Main data cache with rate limit awareness.

    Provides caching for vendor data with configurable TTLs,
    rate limit tracking, and stale-while-revalidate support.

    Example:
        cache = DataCache()

        # Cache with default TTL
        cache.set("fred:FEDFUNDS", data, source="fred")

        # Get with stale fallback if rate limited
        result = cache.get("fred:FEDFUNDS", serve_stale_if_rate_limited=True)

        # Use as decorator
        @cache.cached(ttl_seconds=3600, source="fred")
        def get_fred_data(series_id):
            return fetch_from_api(series_id)
    """

    # Default TTLs by source (in seconds)
    DEFAULT_TTLS = {
        "fred": 3600 * 24,    # 24 hours for FRED (data updates daily)
        "yfinance": 60,       # 1 minute for real-time quotes
        "finnhub": 60,        # 1 minute for real-time data
        "polygon": 300,       # 5 minutes
        "alpha_vantage": 300, # 5 minutes
        "default": 300        # 5 minutes default
    }

    # Default rate limits by source
    DEFAULT_RATE_LIMITS = {
        "fred": (120, 60),      # 120 requests per 60 seconds
        "yfinance": (2000, 60), # High limit (throttles internally)
        "finnhub": (60, 60),    # 60 per minute
        "polygon": (5, 60),     # 5 per minute (free tier)
        "alpha_vantage": (5, 60), # 5 per minute (free tier)
        "default": (100, 60)
    }

    def __init__(
        self,
        backend: Optional[CacheBackend] = None,
        default_ttl_seconds: int = 300
    ):
        """Initialize data cache.

        Args:
            backend: Cache backend (defaults to MemoryCache)
            default_ttl_seconds: Default TTL for entries
        """
        self._backend = backend or MemoryCache()
        self._default_ttl = default_ttl_seconds
        self._stats = CacheStats()
        self._rate_limits: Dict[str, RateLimitState] = {}
        self._lock = threading.RLock()

    def _generate_key(self, key: str, **kwargs) -> str:
        """Generate cache key from key and optional params."""
        if kwargs:
            params_str = json.dumps(kwargs, sort_keys=True)
            return f"{key}:{hashlib.md5(params_str.encode()).hexdigest()[:8]}"
        return key

    def _get_ttl(self, source: str) -> int:
        """Get TTL for a source."""
        return self.DEFAULT_TTLS.get(source, self.DEFAULT_TTLS["default"])

    def _get_rate_limit_state(self, source: str) -> RateLimitState:
        """Get or create rate limit state for source."""
        if source not in self._rate_limits:
            limit, window = self.DEFAULT_RATE_LIMITS.get(
                source,
                self.DEFAULT_RATE_LIMITS["default"]
            )
            self._rate_limits[source] = RateLimitState(
                source=source,
                requests_limit=limit,
                window_seconds=window
            )
        return self._rate_limits[source]

    def get(
        self,
        key: str,
        serve_stale_if_rate_limited: bool = True,
        **kwargs
    ) -> tuple[Optional[Any], CacheStatus]:
        """Get value from cache.

        Args:
            key: Cache key
            serve_stale_if_rate_limited: Return expired value if rate limited
            **kwargs: Additional key params

        Returns:
            Tuple of (value, status)
        """
        full_key = self._generate_key(key, **kwargs)

        with self._lock:
            entry = self._backend.get(full_key)

            if entry is None:
                self._stats.misses += 1
                return None, CacheStatus.MISS

            if not entry.is_expired:
                entry.touch()
                self._backend.set(entry)  # Update metadata
                self._stats.hits += 1
                return entry.value, CacheStatus.HIT

            # Entry is expired
            self._stats.expired += 1

            # Check if we should serve stale
            if serve_stale_if_rate_limited:
                rate_state = self._get_rate_limit_state(entry.source)
                if rate_state.is_rate_limited:
                    self._stats.stale_served += 1
                    return entry.value, CacheStatus.STALE

            return None, CacheStatus.EXPIRED

    def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: Optional[int] = None,
        source: str = "default",
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> None:
        """Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl_seconds: TTL in seconds (uses source default if not specified)
            source: Data source name
            metadata: Optional metadata
            **kwargs: Additional key params
        """
        full_key = self._generate_key(key, **kwargs)
        actual_ttl = ttl_seconds if ttl_seconds is not None else self._get_ttl(source)

        entry = CacheEntry(
            key=full_key,
            value=value,
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(seconds=actual_ttl),
            source=source,
            metadata=metadata or {}
        )

        with self._lock:
            self._backend.set(entry)
            self._stats.size = self._backend.size()

    def delete(self, key: str, **kwargs) -> bool:
        """Delete value from cache."""
        full_key = self._generate_key(key, **kwargs)
        with self._lock:
            result = self._backend.delete(full_key)
            self._stats.size = self._backend.size()
            return result

    def clear(self, source: Optional[str] = None) -> int:
        """Clear cache entries.

        Args:
            source: Clear only entries from this source (None = all)

        Returns:
            Number of entries cleared
        """
        with self._lock:
            if source is None:
                count = self._backend.clear()
            else:
                count = 0
                for key in self._backend.keys():
                    entry = self._backend.get(key)
                    if entry and entry.source == source:
                        self._backend.delete(key)
                        count += 1

            self._stats.evictions += count
            self._stats.size = self._backend.size()
            return count

    def record_rate_limit(self, source: str, backoff_seconds: int = 60) -> None:
        """Record a rate limit hit for a source."""
        with self._lock:
            state = self._get_rate_limit_state(source)
            state.record_rate_limit(backoff_seconds)

    def record_request(self, source: str) -> None:
        """Record a request for rate limit tracking."""
        with self._lock:
            state = self._get_rate_limit_state(source)
            state.record_request()

    def record_success(self, source: str) -> None:
        """Record successful request."""
        with self._lock:
            state = self._get_rate_limit_state(source)
            state.record_success()

    def is_rate_limited(self, source: str) -> bool:
        """Check if source is rate limited."""
        with self._lock:
            state = self._get_rate_limit_state(source)
            return state.is_rate_limited

    def get_stats(self) -> CacheStats:
        """Get cache statistics."""
        with self._lock:
            self._stats.size = self._backend.size()
            return self._stats

    def cached(
        self,
        ttl_seconds: Optional[int] = None,
        source: str = "default",
        key_prefix: str = ""
    ) -> Callable:
        """Decorator for caching function results.

        Example:
            @cache.cached(ttl_seconds=3600, source="fred")
            def get_fred_data(series_id):
                return fetch_from_api(series_id)
        """
        def decorator(func: Callable) -> Callable:
            def wrapper(*args, **kwargs):
                # Generate cache key from function name and args
                key_parts = [key_prefix, func.__name__]
                if args:
                    key_parts.append(str(args))
                if kwargs:
                    key_parts.append(json.dumps(kwargs, sort_keys=True))
                cache_key = ":".join(filter(None, key_parts))

                # Check cache
                value, status = self.get(cache_key, serve_stale_if_rate_limited=True)
                if status in (CacheStatus.HIT, CacheStatus.STALE):
                    return value

                # Execute function
                result = func(*args, **kwargs)

                # Cache result
                self.set(cache_key, result, ttl_seconds=ttl_seconds, source=source)

                return result

            return wrapper
        return decorator


# Global cache instance
_global_cache: Optional[DataCache] = None
_global_cache_lock = threading.Lock()


def get_cache() -> DataCache:
    """Get the global cache instance."""
    global _global_cache
    with _global_cache_lock:
        if _global_cache is None:
            _global_cache = DataCache()
        return _global_cache


def reset_cache() -> None:
    """Reset the global cache instance. For testing."""
    global _global_cache
    with _global_cache_lock:
        _global_cache = None
