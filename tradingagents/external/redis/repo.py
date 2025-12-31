from tradingagents.external.redis.client import get_redis_client

redis = get_redis_client()

class RedisRepo:
    def get(self, key: str):
        return redis.get(key)

    def set(self, key: str, value: str, ex: int | None = None):
        return redis.set(key, value, ex=ex)

    def delete(self, key: str):
        return redis.delete(key)

    def exists(self, key: str) -> bool:
        return redis.exists(key) == 1

redis_repo = RedisRepo()
