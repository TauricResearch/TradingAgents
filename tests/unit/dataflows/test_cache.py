"""Tests for data caching layer.

Issue #12: [DATA-11] Data caching layer - FRED rate limits
"""

import pytest
import time
import threading
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from tradingagents.dataflows.cache import (
    CacheEntry,
    CacheStats,
    CacheStatus,
    RateLimitState,
    MemoryCache,
    FileCache,
    DataCache,
    get_cache,
    reset_cache,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def reset_global_cache():
    """Reset global cache before each test."""
    reset_cache()
    yield
    reset_cache()


class TestCacheEntry:
    """Tests for CacheEntry dataclass."""

    def test_entry_creation(self):
        """Test creating a cache entry."""
        entry = CacheEntry(
            key="test_key",
            value={"data": "test"},
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=1),
            source="fred"
        )

        assert entry.key == "test_key"
        assert entry.value == {"data": "test"}
        assert entry.source == "fred"
        assert entry.access_count == 0

    def test_is_expired_false(self):
        """Test is_expired returns False for valid entry."""
        entry = CacheEntry(
            key="test",
            value="data",
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=1)
        )
        assert entry.is_expired is False

    def test_is_expired_true(self):
        """Test is_expired returns True for expired entry."""
        entry = CacheEntry(
            key="test",
            value="data",
            created_at=datetime.now() - timedelta(hours=2),
            expires_at=datetime.now() - timedelta(hours=1)
        )
        assert entry.is_expired is True

    def test_age_seconds(self):
        """Test age_seconds calculation."""
        entry = CacheEntry(
            key="test",
            value="data",
            created_at=datetime.now() - timedelta(seconds=60),
            expires_at=datetime.now() + timedelta(hours=1)
        )
        assert 59 < entry.age_seconds < 61

    def test_ttl_remaining(self):
        """Test ttl_remaining_seconds calculation."""
        entry = CacheEntry(
            key="test",
            value="data",
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(seconds=3600)
        )
        assert 3599 < entry.ttl_remaining_seconds <= 3600

    def test_touch_updates_metadata(self):
        """Test touch updates access metadata."""
        entry = CacheEntry(
            key="test",
            value="data",
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=1)
        )

        assert entry.access_count == 0
        assert entry.last_accessed is None

        entry.touch()

        assert entry.access_count == 1
        assert entry.last_accessed is not None


class TestCacheStats:
    """Tests for CacheStats dataclass."""

    def test_default_values(self):
        """Test default values."""
        stats = CacheStats()
        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.hit_rate == 0.0

    def test_hit_rate_calculation(self):
        """Test hit rate calculation."""
        stats = CacheStats(hits=75, misses=25)
        assert stats.hit_rate == 75.0

    def test_hit_rate_no_requests(self):
        """Test hit rate with no requests."""
        stats = CacheStats()
        assert stats.hit_rate == 0.0

    def test_to_dict(self):
        """Test conversion to dictionary."""
        stats = CacheStats(hits=10, misses=5, evictions=2)
        d = stats.to_dict()

        assert d["hits"] == 10
        assert d["misses"] == 5
        assert d["evictions"] == 2
        assert "hit_rate" in d


class TestRateLimitState:
    """Tests for RateLimitState dataclass."""

    def test_default_values(self):
        """Test default values."""
        state = RateLimitState(source="fred")
        assert state.source == "fred"
        assert state.requests_made == 0
        assert state.is_rate_limited is False

    def test_record_request(self):
        """Test recording requests."""
        state = RateLimitState(source="test", requests_limit=5)

        for i in range(3):
            state.record_request()

        assert state.requests_made == 3
        assert state.requests_remaining == 2

    def test_is_rate_limited_after_backoff(self):
        """Test rate limiting after recording limit hit."""
        state = RateLimitState(source="test")

        assert state.is_rate_limited is False

        state.record_rate_limit(backoff_seconds=1)

        assert state.is_rate_limited is True

        # Wait for backoff to expire
        time.sleep(1.1)
        assert state.is_rate_limited is False

    def test_record_success_clears_backoff(self):
        """Test that success clears backoff."""
        state = RateLimitState(source="test")
        state.record_rate_limit(backoff_seconds=60)
        assert state.is_rate_limited is True

        state.record_success()
        assert state.is_rate_limited is False
        assert state.consecutive_failures == 0

    def test_exponential_backoff(self):
        """Test exponential backoff on consecutive failures."""
        state = RateLimitState(source="test")

        # First failure - 1 second backoff
        state.record_rate_limit(backoff_seconds=1)
        assert state.consecutive_failures == 1

        # Simulate recovery
        state.backoff_until = None

        # Second failure - 2 second backoff
        state.record_rate_limit(backoff_seconds=1)
        assert state.consecutive_failures == 2


class TestMemoryCache:
    """Tests for MemoryCache backend."""

    def test_get_set(self):
        """Test basic get/set operations."""
        cache = MemoryCache()

        entry = CacheEntry(
            key="test",
            value="data",
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=1)
        )

        cache.set(entry)
        result = cache.get("test")

        assert result is not None
        assert result.value == "data"

    def test_get_missing(self):
        """Test getting missing key."""
        cache = MemoryCache()
        assert cache.get("nonexistent") is None

    def test_delete(self):
        """Test deleting entry."""
        cache = MemoryCache()

        entry = CacheEntry(
            key="test",
            value="data",
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=1)
        )

        cache.set(entry)
        assert cache.delete("test") is True
        assert cache.get("test") is None

    def test_delete_missing(self):
        """Test deleting missing key."""
        cache = MemoryCache()
        assert cache.delete("nonexistent") is False

    def test_clear(self):
        """Test clearing cache."""
        cache = MemoryCache()

        for i in range(5):
            cache.set(CacheEntry(
                key=f"key_{i}",
                value=f"value_{i}",
                created_at=datetime.now(),
                expires_at=datetime.now() + timedelta(hours=1)
            ))

        count = cache.clear()
        assert count == 5
        assert cache.size() == 0

    def test_lru_eviction(self):
        """Test LRU eviction when at capacity."""
        cache = MemoryCache(max_size=3)

        # Add 3 entries
        for i in range(3):
            cache.set(CacheEntry(
                key=f"key_{i}",
                value=f"value_{i}",
                created_at=datetime.now(),
                expires_at=datetime.now() + timedelta(hours=1)
            ))

        # Access key_1 to make it recently used
        cache.get("key_1")

        # Add new entry, should evict key_0 (least recently used)
        cache.set(CacheEntry(
            key="key_3",
            value="value_3",
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=1)
        ))

        assert cache.size() == 3
        assert cache.get("key_0") is None
        assert cache.get("key_1") is not None

    def test_thread_safety(self):
        """Test thread-safe operations."""
        cache = MemoryCache()
        errors = []

        def write_entries(start):
            try:
                for i in range(100):
                    cache.set(CacheEntry(
                        key=f"key_{start}_{i}",
                        value=f"value_{start}_{i}",
                        created_at=datetime.now(),
                        expires_at=datetime.now() + timedelta(hours=1)
                    ))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=write_entries, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert cache.size() == 500


class TestFileCache:
    """Tests for FileCache backend."""

    def test_get_set(self):
        """Test basic get/set operations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = FileCache(cache_dir=Path(tmpdir))

            entry = CacheEntry(
                key="test",
                value={"data": "test"},
                created_at=datetime.now(),
                expires_at=datetime.now() + timedelta(hours=1),
                source="test"
            )

            cache.set(entry)
            result = cache.get("test")

            assert result is not None
            assert result.value == {"data": "test"}
            assert result.source == "test"

    def test_get_missing(self):
        """Test getting missing key."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = FileCache(cache_dir=Path(tmpdir))
            assert cache.get("nonexistent") is None

    def test_delete(self):
        """Test deleting entry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = FileCache(cache_dir=Path(tmpdir))

            entry = CacheEntry(
                key="test",
                value="data",
                created_at=datetime.now(),
                expires_at=datetime.now() + timedelta(hours=1)
            )

            cache.set(entry)
            assert cache.delete("test") is True
            assert cache.get("test") is None

    def test_clear(self):
        """Test clearing cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = FileCache(cache_dir=Path(tmpdir))

            for i in range(3):
                cache.set(CacheEntry(
                    key=f"key_{i}",
                    value=f"value_{i}",
                    created_at=datetime.now(),
                    expires_at=datetime.now() + timedelta(hours=1)
                ))

            count = cache.clear()
            assert count == 3
            assert cache.size() == 0


class TestDataCache:
    """Tests for DataCache main class."""

    def test_get_set_basic(self):
        """Test basic get/set operations."""
        cache = DataCache()

        cache.set("test_key", {"data": "test"}, source="fred")
        value, status = cache.get("test_key")

        assert status == CacheStatus.HIT
        assert value == {"data": "test"}

    def test_get_miss(self):
        """Test cache miss."""
        cache = DataCache()

        value, status = cache.get("nonexistent")

        assert status == CacheStatus.MISS
        assert value is None

    def test_get_expired(self):
        """Test getting expired entry."""
        cache = DataCache()

        # Set with very short TTL
        cache.set("test", "data", ttl_seconds=0, source="test")

        # Wait for expiration
        time.sleep(0.1)

        value, status = cache.get("test", serve_stale_if_rate_limited=False)

        assert status == CacheStatus.EXPIRED
        assert value is None

    def test_serve_stale_when_rate_limited(self):
        """Test serving stale data when rate limited."""
        cache = DataCache()

        # Set entry that will expire
        cache.set("test", "stale_data", ttl_seconds=0, source="test")
        time.sleep(0.1)

        # Simulate rate limit
        cache.record_rate_limit("test", backoff_seconds=60)

        # Should get stale data
        value, status = cache.get("test", serve_stale_if_rate_limited=True)

        assert status == CacheStatus.STALE
        assert value == "stale_data"

    def test_delete(self):
        """Test deleting entry."""
        cache = DataCache()

        cache.set("test", "data", source="test")
        assert cache.delete("test") is True

        value, status = cache.get("test")
        assert status == CacheStatus.MISS

    def test_clear_all(self):
        """Test clearing all entries."""
        cache = DataCache()

        cache.set("key1", "value1", source="fred")
        cache.set("key2", "value2", source="yfinance")

        count = cache.clear()
        assert count == 2

    def test_clear_by_source(self):
        """Test clearing entries by source."""
        cache = DataCache()

        cache.set("fred_key", "fred_data", source="fred")
        cache.set("yf_key", "yf_data", source="yfinance")

        count = cache.clear(source="fred")
        assert count == 1

        # yfinance entry should still exist
        value, status = cache.get("yf_key")
        assert status == CacheStatus.HIT

    def test_key_with_params(self):
        """Test key generation with params."""
        cache = DataCache()

        cache.set("series", "data1", source="fred", series_id="FEDFUNDS")
        cache.set("series", "data2", source="fred", series_id="DGS10")

        value1, _ = cache.get("series", series_id="FEDFUNDS")
        value2, _ = cache.get("series", series_id="DGS10")

        assert value1 == "data1"
        assert value2 == "data2"

    def test_stats_tracking(self):
        """Test statistics tracking."""
        cache = DataCache()

        # Miss
        cache.get("missing")

        # Hit
        cache.set("present", "data", source="test")
        cache.get("present")
        cache.get("present")

        stats = cache.get_stats()
        assert stats.misses == 1
        assert stats.hits == 2

    def test_rate_limit_tracking(self):
        """Test rate limit state tracking."""
        cache = DataCache()

        assert cache.is_rate_limited("fred") is False

        cache.record_rate_limit("fred", backoff_seconds=1)
        assert cache.is_rate_limited("fred") is True

        time.sleep(1.1)
        assert cache.is_rate_limited("fred") is False

    def test_cached_decorator(self):
        """Test @cached decorator."""
        cache = DataCache()
        call_count = [0]

        @cache.cached(ttl_seconds=300, source="test")
        def expensive_function(x):
            call_count[0] += 1
            return x * 2

        # First call - executes function
        result1 = expensive_function(5)
        assert result1 == 10
        assert call_count[0] == 1

        # Second call - from cache
        result2 = expensive_function(5)
        assert result2 == 10
        assert call_count[0] == 1

        # Different argument - executes function
        result3 = expensive_function(10)
        assert result3 == 20
        assert call_count[0] == 2

    def test_default_ttls_by_source(self):
        """Test default TTLs are applied by source."""
        cache = DataCache()

        # FRED default is 24 hours
        cache.set("fred_data", "data", source="fred")
        entry = cache._backend.get(cache._generate_key("fred_data"))

        # Should have ~24 hour TTL
        assert entry.ttl_remaining_seconds > 3600 * 23


class TestGlobalCache:
    """Tests for global cache functions."""

    def test_get_cache_singleton(self):
        """Test get_cache returns singleton."""
        cache1 = get_cache()
        cache2 = get_cache()
        assert cache1 is cache2

    def test_reset_cache(self):
        """Test reset_cache creates new instance."""
        cache1 = get_cache()
        reset_cache()
        cache2 = get_cache()
        assert cache1 is not cache2


class TestCacheIntegration:
    """Integration tests for cache with rate limiting."""

    def test_rate_limited_fetch_pattern(self):
        """Test typical pattern: cache + rate limit handling."""
        cache = DataCache()
        fetch_count = [0]

        def fetch_data(key):
            """Simulate data fetch with rate limit."""
            # Check rate limit first
            if cache.is_rate_limited("api"):
                # Try stale cache
                value, status = cache.get(key, serve_stale_if_rate_limited=True)
                if status == CacheStatus.STALE:
                    return value
                raise RuntimeError("Rate limited and no stale data")

            # Check cache
            value, status = cache.get(key)
            if status == CacheStatus.HIT:
                return value

            # Fetch fresh data
            fetch_count[0] += 1
            cache.record_request("api")

            # Simulate API response
            data = f"data_for_{key}"

            cache.set(key, data, source="api", ttl_seconds=1)
            cache.record_success("api")

            return data

        # First fetch - from API
        result1 = fetch_data("key1")
        assert result1 == "data_for_key1"
        assert fetch_count[0] == 1

        # Second fetch - from cache
        result2 = fetch_data("key1")
        assert result2 == "data_for_key1"
        assert fetch_count[0] == 1  # No additional fetch

        # Wait for expiration and simulate rate limit
        time.sleep(1.1)
        cache.record_rate_limit("api", backoff_seconds=60)

        # Should get stale data
        result3 = fetch_data("key1")
        assert result3 == "data_for_key1"
        assert fetch_count[0] == 1  # Still no additional fetch
