"""
Redis Cache Layer
=================

High-performance caching with Redis for market data, AI decisions,
and expensive computations.
"""

import json
import logging
import pickle
from typing import Any, Optional, Dict, List, Union
from datetime import datetime, timedelta
from decimal import Decimal
import hashlib
import asyncio

import redis.asyncio as redis
from redis.asyncio.lock import Lock
from redis.exceptions import RedisError, ConnectionError

logger = logging.getLogger(__name__)


class CacheKey:
    """Cache key builder with namespacing"""

    # Namespaces
    MARKET_DATA = "market"
    AI_DECISION = "ai"
    SIGNAL = "signal"
    CONGRESSIONAL = "congress"
    NEWS = "news"
    TECHNICAL = "tech"
    POSITION = "position"
    METRICS = "metrics"

    @staticmethod
    def build(*parts: Union[str, int, float]) -> str:
        """Build a cache key from parts"""
        return ":".join(str(p) for p in parts)

    @staticmethod
    def market_data(ticker: str) -> str:
        """Key for market data"""
        return CacheKey.build(CacheKey.MARKET_DATA, ticker)

    @staticmethod
    def ai_decision(ticker: str, date: str) -> str:
        """Key for AI trading decision"""
        return CacheKey.build(CacheKey.AI_DECISION, ticker, date)

    @staticmethod
    def signal(ticker: str, signal_type: str) -> str:
        """Key for trading signal"""
        return CacheKey.build(CacheKey.SIGNAL, ticker, signal_type)

    @staticmethod
    def congressional_trades(days_back: int) -> str:
        """Key for congressional trades"""
        return CacheKey.build(CacheKey.CONGRESSIONAL, f"last_{days_back}_days")

    @staticmethod
    def news_sentiment(ticker: str) -> str:
        """Key for news sentiment"""
        return CacheKey.build(CacheKey.NEWS, ticker, "sentiment")

    @staticmethod
    def technical_indicators(ticker: str) -> str:
        """Key for technical indicators"""
        return CacheKey.build(CacheKey.TECHNICAL, ticker)

    @staticmethod
    def risk_metrics() -> str:
        """Key for risk metrics"""
        return CacheKey.build(CacheKey.METRICS, "risk")


class RedisCache:
    """
    Redis cache manager with connection pooling and error handling
    """

    def __init__(self,
                 host: str = "localhost",
                 port: int = 6379,
                 db: int = 0,
                 password: Optional[str] = None,
                 max_connections: int = 50,
                 socket_timeout: int = 5,
                 retry_on_timeout: bool = True):
        """
        Initialize Redis cache

        Args:
            host: Redis host
            port: Redis port
            db: Redis database number
            password: Redis password
            max_connections: Maximum connection pool size
            socket_timeout: Socket timeout in seconds
            retry_on_timeout: Retry on timeout errors
        """
        self.host = host
        self.port = port
        self.db = db

        # Connection pool for better performance
        self.pool = redis.ConnectionPool(
            host=host,
            port=port,
            db=db,
            password=password,
            max_connections=max_connections,
            socket_timeout=socket_timeout,
            socket_connect_timeout=socket_timeout,
            retry_on_timeout=retry_on_timeout,
            decode_responses=False  # Handle encoding ourselves
        )

        self.redis: Optional[redis.Redis] = None
        self.connected = False

        # Default TTLs (seconds)
        self.default_ttls = {
            CacheKey.MARKET_DATA: 60,  # 1 minute for market data
            CacheKey.AI_DECISION: 3600,  # 1 hour for AI decisions
            CacheKey.SIGNAL: 300,  # 5 minutes for signals
            CacheKey.CONGRESSIONAL: 3600,  # 1 hour for congressional
            CacheKey.NEWS: 1800,  # 30 minutes for news
            CacheKey.TECHNICAL: 300,  # 5 minutes for technical
            CacheKey.METRICS: 60,  # 1 minute for metrics
        }

        # Cache statistics
        self.stats = {
            'hits': 0,
            'misses': 0,
            'errors': 0,
            'evictions': 0
        }

    async def connect(self) -> bool:
        """
        Connect to Redis

        Returns:
            True if connected successfully
        """
        try:
            self.redis = redis.Redis(connection_pool=self.pool)

            # Test connection
            await self.redis.ping()

            self.connected = True
            logger.info(f"Connected to Redis at {self.host}:{self.port}")

            # Set memory policy
            await self._configure_memory_policy()

            return True

        except (RedisError, ConnectionError) as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self.connected = False
            return False

    async def disconnect(self):
        """Disconnect from Redis"""
        if self.redis:
            await self.redis.close()
            await self.pool.disconnect()
        self.connected = False
        logger.info("Disconnected from Redis")

    async def _configure_memory_policy(self):
        """Configure Redis memory policy"""
        try:
            # Set max memory policy to LRU (Least Recently Used)
            await self.redis.config_set('maxmemory-policy', 'allkeys-lru')

            # Set max memory (optional, depends on your setup)
            # await self.redis.config_set('maxmemory', '1gb')

        except Exception as e:
            logger.warning(f"Could not configure memory policy: {e}")

    # === Core Cache Operations ===

    async def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found
        """
        if not self.connected:
            return None

        try:
            value = await self.redis.get(key)

            if value is None:
                self.stats['misses'] += 1
                return None

            self.stats['hits'] += 1

            # Deserialize based on data type
            return self._deserialize(value)

        except Exception as e:
            logger.error(f"Cache get error for {key}: {e}")
            self.stats['errors'] += 1
            return None

    async def set(self,
                  key: str,
                  value: Any,
                  ttl: Optional[int] = None,
                  nx: bool = False) -> bool:
        """
        Set value in cache

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds
            nx: Only set if key doesn't exist

        Returns:
            True if set successfully
        """
        if not self.connected:
            return False

        try:
            # Determine TTL
            if ttl is None:
                namespace = key.split(':')[0]
                ttl = self.default_ttls.get(namespace, 300)

            # Serialize value
            serialized = self._serialize(value)

            # Set with TTL
            if nx:
                result = await self.redis.set(key, serialized, ex=ttl, nx=True)
            else:
                result = await self.redis.setex(key, ttl, serialized)

            return bool(result)

        except Exception as e:
            logger.error(f"Cache set error for {key}: {e}")
            self.stats['errors'] += 1
            return False

    async def delete(self, *keys: str) -> int:
        """
        Delete keys from cache

        Args:
            *keys: Keys to delete

        Returns:
            Number of keys deleted
        """
        if not self.connected or not keys:
            return 0

        try:
            return await self.redis.delete(*keys)
        except Exception as e:
            logger.error(f"Cache delete error: {e}")
            return 0

    async def exists(self, key: str) -> bool:
        """
        Check if key exists

        Args:
            key: Cache key

        Returns:
            True if exists
        """
        if not self.connected:
            return False

        try:
            return bool(await self.redis.exists(key))
        except Exception:
            return False

    async def expire(self, key: str, ttl: int) -> bool:
        """
        Set expiration on key

        Args:
            key: Cache key
            ttl: Time to live in seconds

        Returns:
            True if expiration set
        """
        if not self.connected:
            return False

        try:
            return bool(await self.redis.expire(key, ttl))
        except Exception:
            return False

    # === Batch Operations ===

    async def mget(self, keys: List[str]) -> Dict[str, Any]:
        """
        Get multiple values

        Args:
            keys: List of keys

        Returns:
            Dictionary of key-value pairs
        """
        if not self.connected or not keys:
            return {}

        try:
            values = await self.redis.mget(keys)
            result = {}

            for key, value in zip(keys, values):
                if value is not None:
                    result[key] = self._deserialize(value)
                    self.stats['hits'] += 1
                else:
                    self.stats['misses'] += 1

            return result

        except Exception as e:
            logger.error(f"Cache mget error: {e}")
            return {}

    async def mset(self,
                   data: Dict[str, Any],
                   ttl: Optional[int] = None) -> bool:
        """
        Set multiple values

        Args:
            data: Dictionary of key-value pairs
            ttl: Time to live in seconds

        Returns:
            True if all set successfully
        """
        if not self.connected or not data:
            return False

        try:
            # Use pipeline for atomic operations
            pipe = self.redis.pipeline()

            for key, value in data.items():
                serialized = self._serialize(value)

                if ttl is None:
                    namespace = key.split(':')[0]
                    key_ttl = self.default_ttls.get(namespace, 300)
                else:
                    key_ttl = ttl

                pipe.setex(key, key_ttl, serialized)

            results = await pipe.execute()
            return all(results)

        except Exception as e:
            logger.error(f"Cache mset error: {e}")
            return False

    # === Pattern Operations ===

    async def keys_pattern(self, pattern: str) -> List[str]:
        """
        Get keys matching pattern

        Args:
            pattern: Redis pattern (e.g., "market:*")

        Returns:
            List of matching keys
        """
        if not self.connected:
            return []

        try:
            keys = await self.redis.keys(pattern)
            return [k.decode('utf-8') if isinstance(k, bytes) else k for k in keys]
        except Exception as e:
            logger.error(f"Cache keys error: {e}")
            return []

    async def delete_pattern(self, pattern: str) -> int:
        """
        Delete keys matching pattern

        Args:
            pattern: Redis pattern

        Returns:
            Number of keys deleted
        """
        keys = await self.keys_pattern(pattern)
        if keys:
            return await self.delete(*keys)
        return 0

    # === Distributed Locking ===

    async def acquire_lock(self,
                          name: str,
                          timeout: int = 10,
                          blocking: bool = True) -> Optional[Lock]:
        """
        Acquire distributed lock

        Args:
            name: Lock name
            timeout: Lock timeout in seconds
            blocking: Whether to block waiting for lock

        Returns:
            Lock object or None
        """
        if not self.connected:
            return None

        try:
            lock = Lock(
                self.redis,
                f"lock:{name}",
                timeout=timeout,
                blocking=blocking,
                blocking_timeout=5 if blocking else 0
            )

            if await lock.acquire():
                return lock
            return None

        except Exception as e:
            logger.error(f"Lock acquire error: {e}")
            return None

    # === Specialized Cache Methods ===

    async def cache_market_data(self,
                               ticker: str,
                               data: Dict[str, Any],
                               ttl: int = 60) -> bool:
        """
        Cache market data with automatic expiration

        Args:
            ticker: Stock ticker
            data: Market data dictionary
            ttl: Time to live in seconds

        Returns:
            True if cached successfully
        """
        key = CacheKey.market_data(ticker)

        # Add timestamp
        data['cached_at'] = datetime.now().isoformat()

        return await self.set(key, data, ttl)

    async def get_market_data(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Get cached market data

        Args:
            ticker: Stock ticker

        Returns:
            Market data or None
        """
        key = CacheKey.market_data(ticker)
        data = await self.get(key)

        if data and isinstance(data, dict):
            # Check if data is stale (older than 2 minutes)
            cached_at = data.get('cached_at')
            if cached_at:
                cache_time = datetime.fromisoformat(cached_at)
                if (datetime.now() - cache_time).seconds > 120:
                    # Data is stale, delete it
                    await self.delete(key)
                    return None

        return data

    async def cache_ai_decision(self,
                               ticker: str,
                               date: str,
                               decision: str,
                               ttl: int = 3600) -> bool:
        """
        Cache AI trading decision

        Args:
            ticker: Stock ticker
            date: Analysis date
            decision: AI decision
            ttl: Time to live (default 1 hour)

        Returns:
            True if cached successfully
        """
        key = CacheKey.ai_decision(ticker, date)

        data = {
            'decision': decision,
            'ticker': ticker,
            'date': date,
            'cached_at': datetime.now().isoformat()
        }

        return await self.set(key, data, ttl)

    async def get_ai_decision(self,
                             ticker: str,
                             date: str) -> Optional[str]:
        """
        Get cached AI decision

        Args:
            ticker: Stock ticker
            date: Analysis date

        Returns:
            AI decision or None
        """
        key = CacheKey.ai_decision(ticker, date)
        data = await self.get(key)

        if data and isinstance(data, dict):
            return data.get('decision')
        return None

    async def invalidate_ticker(self, ticker: str):
        """
        Invalidate all cache entries for a ticker

        Args:
            ticker: Stock ticker
        """
        patterns = [
            f"{CacheKey.MARKET_DATA}:{ticker}*",
            f"{CacheKey.AI_DECISION}:{ticker}*",
            f"{CacheKey.SIGNAL}:{ticker}*",
            f"{CacheKey.TECHNICAL}:{ticker}*",
            f"{CacheKey.NEWS}:{ticker}*"
        ]

        for pattern in patterns:
            await self.delete_pattern(pattern)

    # === Helper Methods ===

    def _serialize(self, value: Any) -> bytes:
        """
        Serialize value for storage

        Args:
            value: Value to serialize

        Returns:
            Serialized bytes
        """
        # Handle different types
        if isinstance(value, (str, int, float)):
            return json.dumps(value).encode('utf-8')
        elif isinstance(value, Decimal):
            return json.dumps(str(value)).encode('utf-8')
        elif isinstance(value, (dict, list)):
            return json.dumps(value, default=str).encode('utf-8')
        else:
            # Use pickle for complex objects
            return pickle.dumps(value)

    def _deserialize(self, value: bytes) -> Any:
        """
        Deserialize value from storage

        Args:
            value: Serialized bytes

        Returns:
            Deserialized value
        """
        if not value:
            return None

        # Try JSON first
        try:
            decoded = value.decode('utf-8')
            return json.loads(decoded)
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

        # Try pickle
        try:
            return pickle.loads(value)
        except Exception as e:
            logger.error(f"Deserialization error: {e}")
            return None

    async def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics

        Returns:
            Statistics dictionary
        """
        info = {}

        if self.connected:
            try:
                # Get Redis server info
                redis_info = await self.redis.info('stats')
                info['redis'] = {
                    'total_connections': redis_info.get('total_connections_received', 0),
                    'commands_processed': redis_info.get('total_commands_processed', 0),
                    'keyspace_hits': redis_info.get('keyspace_hits', 0),
                    'keyspace_misses': redis_info.get('keyspace_misses', 0),
                }

                # Get memory info
                memory_info = await self.redis.info('memory')
                info['memory'] = {
                    'used_memory': memory_info.get('used_memory_human', '0'),
                    'peak_memory': memory_info.get('used_memory_peak_human', '0'),
                }

                # Get database size
                info['db_size'] = await self.redis.dbsize()

            except Exception as e:
                logger.error(f"Error getting Redis stats: {e}")

        # Add local stats
        total_requests = self.stats['hits'] + self.stats['misses']
        hit_rate = (self.stats['hits'] / total_requests * 100) if total_requests > 0 else 0

        info['cache_stats'] = {
            **self.stats,
            'hit_rate': f"{hit_rate:.1f}%",
            'total_requests': total_requests
        }

        return info

    async def clear_all(self) -> bool:
        """
        Clear all cache (USE WITH CAUTION)

        Returns:
            True if cleared successfully
        """
        if not self.connected:
            return False

        try:
            await self.redis.flushdb()
            logger.warning("Cache cleared - all data deleted")
            return True
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
            return False


# === Cache Decorator ===

def cached(ttl: int = 300, key_prefix: str = ""):
    """
    Decorator for caching function results

    Args:
        ttl: Time to live in seconds
        key_prefix: Prefix for cache key
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Build cache key from function name and arguments
            cache_key_parts = [key_prefix or func.__name__]

            # Add args to key
            for arg in args:
                if hasattr(arg, '__dict__'):
                    # Skip object instances
                    continue
                cache_key_parts.append(str(arg))

            # Add kwargs to key
            for k, v in sorted(kwargs.items()):
                cache_key_parts.append(f"{k}={v}")

            cache_key = ":".join(cache_key_parts)

            # Try to get from cache
            if hasattr(wrapper, '_cache'):
                cached_value = await wrapper._cache.get(cache_key)
                if cached_value is not None:
                    return cached_value

            # Call function
            result = await func(*args, **kwargs)

            # Cache result
            if hasattr(wrapper, '_cache') and result is not None:
                await wrapper._cache.set(cache_key, result, ttl)

            return result

        return wrapper
    return decorator


# === Cache Manager Singleton ===

class CacheManager:
    """Singleton cache manager"""

    _instance: Optional[RedisCache] = None

    @classmethod
    def get_instance(cls) -> RedisCache:
        """Get or create cache instance"""
        if cls._instance is None:
            cls._instance = RedisCache()
        return cls._instance

    @classmethod
    async def initialize(cls,
                         host: str = "localhost",
                         port: int = 6379,
                         **kwargs) -> RedisCache:
        """
        Initialize cache manager

        Args:
            host: Redis host
            port: Redis port
            **kwargs: Additional Redis options

        Returns:
            Redis cache instance
        """
        cls._instance = RedisCache(host, port, **kwargs)
        await cls._instance.connect()
        return cls._instance


# Example usage
async def main():
    """Example of using the cache layer"""

    # Initialize cache
    cache = await CacheManager.initialize()

    # Cache market data
    market_data = {
        'last': 150.25,
        'bid': 150.20,
        'ask': 150.30,
        'volume': 1000000
    }
    await cache.cache_market_data("AAPL", market_data)

    # Get cached data
    cached = await cache.get_market_data("AAPL")
    print(f"Cached market data: {cached}")

    # Cache AI decision
    await cache.cache_ai_decision("NVDA", "2024-01-01", "BUY with high confidence")

    # Get cached decision
    decision = await cache.get_ai_decision("NVDA", "2024-01-01")
    print(f"Cached AI decision: {decision}")

    # Get cache statistics
    stats = await cache.get_stats()
    print(f"Cache stats: {stats}")

    # Clean up
    await cache.disconnect()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())