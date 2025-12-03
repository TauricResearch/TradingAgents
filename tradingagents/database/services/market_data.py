import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from tradingagents.database.models import DataCache
from tradingagents.database.repositories import DataCacheRepository

logger = logging.getLogger(__name__)


class MarketDataService:
    def __init__(self, session: Session):
        self.session = session
        self.cache_repo = DataCacheRepository(session)

    def _generate_cache_key(
        self,
        method: str,
        ticker: str | None = None,
        date: str | None = None,
        **kwargs: Any,
    ) -> str:
        key_parts = [method]
        if ticker:
            key_parts.append(ticker)
        if date:
            key_parts.append(date)
        for k, v in sorted(kwargs.items()):
            key_parts.append(f"{k}={v}")
        key_string = ":".join(key_parts)
        return hashlib.sha256(key_string.encode()).hexdigest()[:32]

    def get_cached_data(
        self,
        method: str,
        ticker: str | None = None,
        date: str | None = None,
        **kwargs: Any,
    ) -> Any | None:
        cache_key = self._generate_cache_key(method, ticker, date, **kwargs)
        cache_entry = self.cache_repo.get_valid_cache(cache_key)

        if cache_entry and cache_entry.cached_data:
            logger.debug("Cache hit for %s (key: %s)", method, cache_key[:8])
            try:
                return json.loads(cache_entry.cached_data)
            except json.JSONDecodeError:
                return cache_entry.cached_data

        logger.debug("Cache miss for %s (key: %s)", method, cache_key[:8])
        return None

    def set_cached_data(
        self,
        method: str,
        data: Any,
        ticker: str | None = None,
        date: str | None = None,
        ttl_hours: int = 24,
        **kwargs: Any,
    ) -> DataCache:
        cache_key = self._generate_cache_key(method, ticker, date, **kwargs)
        expires_at = datetime.utcnow() + timedelta(hours=ttl_hours)

        cached_data = data if isinstance(data, str) else json.dumps(data)

        logger.debug(
            "Caching data for %s (key: %s, ttl: %dh)",
            method,
            cache_key[:8],
            ttl_hours,
        )

        return self.cache_repo.set_cache(
            cache_key=cache_key,
            data_type=method,
            cached_data=cached_data,
            expires_at=expires_at,
            ticker=ticker,
        )

    def get_or_fetch(
        self,
        method: str,
        fetch_func: callable,
        ticker: str | None = None,
        date: str | None = None,
        ttl_hours: int = 24,
        **kwargs: Any,
    ) -> Any:
        cached = self.get_cached_data(method, ticker, date, **kwargs)
        if cached is not None:
            return cached

        logger.debug("Fetching fresh data for %s", method)
        result = fetch_func()

        if result:
            self.set_cached_data(method, result, ticker, date, ttl_hours, **kwargs)

        return result

    def clear_expired_cache(self) -> int:
        count = self.cache_repo.clear_expired()
        logger.info("Cleared %d expired cache entries", count)
        return count

    def invalidate_ticker_cache(self, ticker: str) -> int:
        entries = self.session.query(DataCache).filter(DataCache.ticker == ticker).all()
        count = 0
        for entry in entries:
            self.session.delete(entry)
            count += 1
        self.session.flush()
        logger.info("Invalidated %d cache entries for ticker %s", count, ticker)
        return count


DEFAULT_TTL_HOURS = {
    "get_stock_data": 1,
    "get_indicators": 1,
    "get_fundamentals": 24,
    "get_balance_sheet": 168,
    "get_cashflow": 168,
    "get_income_statement": 168,
    "get_news": 1,
    "get_global_news": 1,
    "get_insider_sentiment": 24,
    "get_insider_transactions": 24,
    "get_bulk_news": 1,
    "quant_indicators": 1,
    "volume_analysis": 1,
    "relative_strength": 4,
    "support_resistance": 1,
    "risk_reward": 1,
}


def get_default_ttl(method: str) -> int:
    return DEFAULT_TTL_HOURS.get(method, 24)
