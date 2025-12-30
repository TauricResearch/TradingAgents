from redis import Redis, ConnectionPool
from redis.backoff import ExponentialBackoff
from redis.retry import Retry
from tradingagents.dataflows.config import get_config

_client = None

def get_redis_client() -> Redis:
    """Get or create Redis client with lazy initialization."""
    global _client
    if _client is None:
        try:
            config = get_config()
            retry = Retry(ExponentialBackoff(), retries=5)

            pool = ConnectionPool(
                host=config["redis"]["REDIS_HOST"],
                port=config["redis"]["REDIS_PORT"],
                password=config["redis"]["REDIS_PASSWORD"],
                db=config["redis"]["REDIS_DB"],
                decode_responses=True,
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
