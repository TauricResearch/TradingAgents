import time
from tradingagents.external.redis.client import get_redis_client
from tradingagents.domain.model import AnalysisMeta, AnalysisStatus
from tradingagents.config import settings
from rq import Queue, Retry
from redis import Redis

ANALYSIS_META_KEY = "analysis:meta:{job_id}"
ANALYSIS_RESULT_KEY = "analysis:result:{job_id}"
ANALYSIS_COOLDOWN_KEY = "tradingagents-analysis-cooldown-{user_id}:{symbol}"

class RedisRepo:
    def __init__(self, redis: Redis):
        self.redis = redis

    def exists(self, key: str) -> bool:
        return self.redis.exists(key) == 1
    
    def create_cooldown_key(self, user_id: str, symbol: str) -> str:
        return ANALYSIS_COOLDOWN_KEY.format(user_id=user_id, symbol=symbol)
    
    def save_cooldown(self, user_id: str, symbol: str, job_id: str, ttl: int = 6 * 3600):
        key = self.create_cooldown_key(user_id, symbol)
        self.redis.set(key, job_id, ex=ttl)

    def get_cooldown(self, user_id: str, symbol: str) -> tuple[str | None, int | None]:
        key = self.create_cooldown_key(user_id, symbol)

        job_id = self.redis.get(key)
        if job_id is None:
            return None, None

        ttl = self.redis.ttl(key)

        # Redis TTL semantics:
        # -2 → key does not exist
        # -1 → key exists but has no expiry
        # >=0 → seconds remaining

        if ttl < 0:
            print(f"WARNING: Cooldown key {key} has invalid TTL {ttl}.")
            ttl = None

        return job_id, ttl


    def _meta_key(self, job_id: str) -> str:
        return ANALYSIS_META_KEY.format(job_id=job_id)

    def _result_key(self, job_id: str) -> str:
        return ANALYSIS_RESULT_KEY.format(job_id=job_id)
    
    def create_analysis_meta(self, meta: AnalysisMeta, ttl: int = 7 * 24 * 3600):
        self.redis.hset(
            self._meta_key(meta.job_id),
            mapping={
                "job_id": meta.job_id,
                "trade_date": meta.trade_date,
                "user_id": meta.user_id,
                "symbol": meta.symbol,
                "status": meta.status.value,
                "updated_at": meta.updated_at,
            },
        )
        self.redis.expire(self._meta_key(meta.job_id), ttl)

    def update_status_analysis_meta(self, job_id: str, status: AnalysisStatus):
        self.redis.hset(
            self._meta_key(job_id),
            mapping={
                "status": status.value,
                "updated_at": time.time(),
            },
        )

    def get_analysis_meta(self, job_id: str) -> AnalysisMeta | None:
        data = self.redis.hgetall(self._meta_key(job_id))
        if not data:
            return None

        return AnalysisMeta(
            job_id=data["job_id"],
            user_id=data["user_id"],
            symbol=data["symbol"],
            trade_date=data["trade_date"],
            status=AnalysisStatus(data["status"]),
            updated_at=float(data["updated_at"]),
            created_at=float(data.get("created_at")),
        )

    def save_result(self, job_id: str, final_trade: str, ttl: int = 7 * 24 * 3600):
        '''
        Save the final trading decision result to Redis. No expiration by default.
        '''
        self.redis.set(self._result_key(job_id), final_trade, ex=ttl)

    def get_result(self, job_id: str) -> str | None:
        return self.redis.get(self._result_key(job_id))


redis_repo = RedisRepo(get_redis_client())
redis_queue = Queue(connection=get_redis_client(), retry=Retry(max=settings.RQ_RETRIES, interval=settings.RQ_INTERVALS))
