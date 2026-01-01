from redis import Redis, ConnectionPool
from redis.backoff import ExponentialBackoff
from redis.retry import Retry
from redis.exceptions import ResponseError, DataError
from tradingagents.config import settings
import logging

_client = None
logger = logging.getLogger(__name__)

def get_redis_client() -> Redis:
    """Get or create Redis client with lazy initialization."""
    global _client
    if _client is None:
        try:
            print(f"INFO: Creating Redis connection pool with host={settings.REDIS_HOST}, port={settings.REDIS_PORT}")
            
            retry = Retry(ExponentialBackoff(), retries=5)

            pool = ConnectionPool(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                password=settings.REDIS_PASSWORD,
                db=settings.REDIS_DB,
                decode_responses=False,  # Set to False to let RQ handle decoding
                encoding='utf-8',
                socket_connect_timeout=5,
                socket_timeout=5,
                health_check_interval=10,
                retry=retry,
            )
            print("INFO: Initializing Redis client")
            _client = Redis(connection_pool=pool)
            print("INFO: Redis client initialized successfully")
            
        except Exception as e:
            print(f"ERROR: Failed to initialize Redis client: {e}")
            raise
    
    return _client
