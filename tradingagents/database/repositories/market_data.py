from datetime import datetime

from sqlalchemy import and_
from sqlalchemy.orm import Session

from tradingagents.database.models.market_data import (
    DataCache,
    FundamentalData,
    NewsArticle,
    SocialMediaPost,
    StockPrice,
    TechnicalIndicator,
)
from tradingagents.database.repositories.base import BaseRepository


class StockPriceRepository(BaseRepository[StockPrice]):
    def __init__(self, session: Session):
        super().__init__(session, StockPrice)

    def get_by_ticker_and_date(self, ticker: str, date: str) -> StockPrice | None:
        return (
            self.session.query(StockPrice)
            .filter(and_(StockPrice.ticker == ticker, StockPrice.date == date))
            .first()
        )

    def get_by_ticker_range(
        self, ticker: str, start_date: str, end_date: str
    ) -> list[StockPrice]:
        return (
            self.session.query(StockPrice)
            .filter(
                and_(
                    StockPrice.ticker == ticker,
                    StockPrice.date >= start_date,
                    StockPrice.date <= end_date,
                )
            )
            .order_by(StockPrice.date)
            .all()
        )

    def upsert(self, data: dict) -> StockPrice:
        existing = self.get_by_ticker_and_date(data["ticker"], data["date"])
        if existing:
            return self.update(existing, data)
        return self.create(data)


class TechnicalIndicatorRepository(BaseRepository[TechnicalIndicator]):
    def __init__(self, session: Session):
        super().__init__(session, TechnicalIndicator)

    def get_by_ticker_date_indicator(
        self, ticker: str, date: str, indicator_name: str
    ) -> TechnicalIndicator | None:
        return (
            self.session.query(TechnicalIndicator)
            .filter(
                and_(
                    TechnicalIndicator.ticker == ticker,
                    TechnicalIndicator.date == date,
                    TechnicalIndicator.indicator_name == indicator_name,
                )
            )
            .first()
        )

    def get_by_ticker_and_date(
        self, ticker: str, date: str
    ) -> list[TechnicalIndicator]:
        return (
            self.session.query(TechnicalIndicator)
            .filter(
                and_(
                    TechnicalIndicator.ticker == ticker,
                    TechnicalIndicator.date == date,
                )
            )
            .all()
        )


class NewsArticleRepository(BaseRepository[NewsArticle]):
    def __init__(self, session: Session):
        super().__init__(session, NewsArticle)

    def get_by_ticker(self, ticker: str, limit: int = 100) -> list[NewsArticle]:
        return (
            self.session.query(NewsArticle)
            .filter(NewsArticle.ticker == ticker)
            .order_by(NewsArticle.published_at.desc())
            .limit(limit)
            .all()
        )

    def get_recent(self, hours: int = 24, limit: int = 100) -> list[NewsArticle]:
        cutoff = datetime.utcnow().timestamp() - (hours * 3600)
        return (
            self.session.query(NewsArticle)
            .filter(NewsArticle.published_at >= datetime.fromtimestamp(cutoff))
            .order_by(NewsArticle.published_at.desc())
            .limit(limit)
            .all()
        )


class SocialMediaPostRepository(BaseRepository[SocialMediaPost]):
    def __init__(self, session: Session):
        super().__init__(session, SocialMediaPost)

    def get_by_ticker(self, ticker: str, limit: int = 100) -> list[SocialMediaPost]:
        return (
            self.session.query(SocialMediaPost)
            .filter(SocialMediaPost.ticker == ticker)
            .order_by(SocialMediaPost.posted_at.desc())
            .limit(limit)
            .all()
        )


class FundamentalDataRepository(BaseRepository[FundamentalData]):
    def __init__(self, session: Session):
        super().__init__(session, FundamentalData)

    def get_by_ticker_and_metric(
        self, ticker: str, metric_name: str
    ) -> FundamentalData | None:
        return (
            self.session.query(FundamentalData)
            .filter(
                and_(
                    FundamentalData.ticker == ticker,
                    FundamentalData.metric_name == metric_name,
                )
            )
            .order_by(FundamentalData.report_date.desc())
            .first()
        )

    def get_all_by_ticker(self, ticker: str) -> list[FundamentalData]:
        return (
            self.session.query(FundamentalData)
            .filter(FundamentalData.ticker == ticker)
            .order_by(FundamentalData.report_date.desc())
            .all()
        )


class DataCacheRepository(BaseRepository[DataCache]):
    def __init__(self, session: Session):
        super().__init__(session, DataCache)

    def get_by_key(self, cache_key: str) -> DataCache | None:
        return (
            self.session.query(DataCache)
            .filter(DataCache.cache_key == cache_key)
            .first()
        )

    def get_valid_cache(self, cache_key: str) -> DataCache | None:
        cache = self.get_by_key(cache_key)
        if cache and cache.expires_at and cache.expires_at > datetime.utcnow():
            return cache
        return None

    def set_cache(
        self,
        cache_key: str,
        data_type: str,
        cached_data: str,
        expires_at: datetime | None = None,
        ticker: str | None = None,
    ) -> DataCache:
        existing = self.get_by_key(cache_key)
        if existing:
            return self.update(
                existing,
                {
                    "data_type": data_type,
                    "cached_data": cached_data,
                    "expires_at": expires_at,
                    "ticker": ticker,
                },
            )
        return self.create(
            {
                "cache_key": cache_key,
                "data_type": data_type,
                "cached_data": cached_data,
                "expires_at": expires_at,
                "ticker": ticker,
            }
        )

    def clear_expired(self) -> int:
        result = (
            self.session.query(DataCache)
            .filter(DataCache.expires_at < datetime.utcnow())
            .delete()
        )
        return result
