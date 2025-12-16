"""
Redis client for production caching

This module provides an optional Redis connection for:
- Task status persistence (survives server restarts)
- Rate limiting across multiple instances
- API response caching

If REDIS_URL is not set, all operations will be no-ops and
the system will fall back to in-memory storage.
"""

import os
import json
import logging
from typing import Optional, Any

logger = logging.getLogger(__name__)

# Redis URL from environment (Railway provides this automatically)
REDIS_URL = os.getenv("REDIS_URL", "")

# Redis client instance (lazy initialization)
_redis_client = None


def get_redis_client():
    """
    Get Redis client instance (lazy initialization).
    Returns None if Redis is not configured.
    """
    global _redis_client
    
    if _redis_client is not None:
        return _redis_client
    
    if not REDIS_URL:
        logger.info("Redis not configured (REDIS_URL not set) - using in-memory storage")
        return None
    
    try:
        import redis
        _redis_client = redis.from_url(
            REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        # Test connection
        _redis_client.ping()
        logger.info("✅ Redis connected successfully")
        return _redis_client
    except Exception as e:
        logger.warning(f"⚠️ Redis connection failed: {e} - using in-memory storage")
        return None


def is_redis_available() -> bool:
    """Check if Redis is available and connected."""
    client = get_redis_client()
    if client is None:
        return False
    try:
        client.ping()
        return True
    except:
        return False


# ============== Task Storage ==============

def save_task_to_redis(task_id: str, data: dict, expire_seconds: int = 86400) -> bool:
    """
    Save task data to Redis.
    
    Args:
        task_id: Unique task identifier
        data: Task data dictionary
        expire_seconds: TTL in seconds (default 24 hours)
    
    Returns:
        True if saved successfully, False otherwise
    """
    client = get_redis_client()
    if client is None:
        return False
    
    try:
        key = f"task:{task_id}"
        client.setex(key, expire_seconds, json.dumps(data, default=str))
        return True
    except Exception as e:
        logger.error(f"Failed to save task to Redis: {e}")
        return False


def get_task_from_redis(task_id: str) -> Optional[dict]:
    """
    Get task data from Redis.
    
    Args:
        task_id: Unique task identifier
    
    Returns:
        Task data dictionary or None if not found
    """
    client = get_redis_client()
    if client is None:
        return None
    
    try:
        key = f"task:{task_id}"
        data = client.get(key)
        if data:
            return json.loads(data)
        return None
    except Exception as e:
        logger.error(f"Failed to get task from Redis: {e}")
        return None


def delete_task_from_redis(task_id: str) -> bool:
    """
    Delete task data from Redis.
    
    Args:
        task_id: Unique task identifier
    
    Returns:
        True if deleted successfully, False otherwise
    """
    client = get_redis_client()
    if client is None:
        return False
    
    try:
        key = f"task:{task_id}"
        client.delete(key)
        return True
    except Exception as e:
        logger.error(f"Failed to delete task from Redis: {e}")
        return False


def update_task_in_redis(task_id: str, updates: dict) -> bool:
    """
    Update specific fields in task data.
    
    Args:
        task_id: Unique task identifier
        updates: Dictionary of fields to update
    
    Returns:
        True if updated successfully, False otherwise
    """
    existing = get_task_from_redis(task_id)
    if existing is None:
        return False
    
    existing.update(updates)
    return save_task_to_redis(task_id, existing)


# ============== Rate Limiting ==============

def check_rate_limit(key: str, max_requests: int, window_seconds: int) -> tuple[bool, int]:
    """
    Check rate limit for a given key.
    
    Args:
        key: Unique identifier (e.g., IP address)
        max_requests: Maximum allowed requests
        window_seconds: Time window in seconds
    
    Returns:
        Tuple of (is_allowed, remaining_requests)
    """
    client = get_redis_client()
    if client is None:
        # If Redis not available, allow all (fall back to in-memory rate limiting)
        return True, max_requests
    
    try:
        rate_key = f"ratelimit:{key}"
        current = client.get(rate_key)
        
        if current is None:
            # First request in window
            client.setex(rate_key, window_seconds, 1)
            return True, max_requests - 1
        
        count = int(current)
        if count >= max_requests:
            return False, 0
        
        client.incr(rate_key)
        return True, max_requests - count - 1
    except Exception as e:
        logger.error(f"Rate limit check failed: {e}")
        return True, max_requests  # Allow on error


# ============== Caching ==============

def cache_set(key: str, value: Any, expire_seconds: int = 3600) -> bool:
    """
    Set a cache value.
    
    Args:
        key: Cache key
        value: Value to cache (will be JSON serialized)
        expire_seconds: TTL in seconds (default 1 hour)
    
    Returns:
        True if cached successfully, False otherwise
    """
    client = get_redis_client()
    if client is None:
        return False
    
    try:
        cache_key = f"cache:{key}"
        client.setex(cache_key, expire_seconds, json.dumps(value, default=str))
        return True
    except Exception as e:
        logger.error(f"Failed to set cache: {e}")
        return False


def cache_get(key: str) -> Optional[Any]:
    """
    Get a cached value.
    
    Args:
        key: Cache key
    
    Returns:
        Cached value or None if not found
    """
    client = get_redis_client()
    if client is None:
        return None
    
    try:
        cache_key = f"cache:{key}"
        data = client.get(cache_key)
        if data:
            return json.loads(data)
        return None
    except Exception as e:
        logger.error(f"Failed to get cache: {e}")
        return None


def cache_delete(key: str) -> bool:
    """
    Delete a cached value.
    
    Args:
        key: Cache key
    
    Returns:
        True if deleted successfully, False otherwise
    """
    client = get_redis_client()
    if client is None:
        return False
    
    try:
        cache_key = f"cache:{key}"
        client.delete(cache_key)
        return True
    except Exception as e:
        logger.error(f"Failed to delete cache: {e}")
        return False
