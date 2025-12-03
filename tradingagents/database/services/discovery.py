import json
from datetime import datetime

from sqlalchemy.orm import Session

from tradingagents.database.models import (
    DiscoveryArticle,
    DiscoveryRun,
    TrendingStockResult,
)
from tradingagents.database.repositories.base import BaseRepository


class DiscoveryRunRepository(BaseRepository[DiscoveryRun]):
    def __init__(self, session: Session):
        super().__init__(session, DiscoveryRun)

    def get_latest(self) -> DiscoveryRun | None:
        return (
            self.session.query(DiscoveryRun)
            .order_by(DiscoveryRun.created_at.desc())
            .first()
        )

    def get_completed(self, limit: int = 10) -> list[DiscoveryRun]:
        return (
            self.session.query(DiscoveryRun)
            .filter(DiscoveryRun.status == "completed")
            .order_by(DiscoveryRun.created_at.desc())
            .limit(limit)
            .all()
        )


class TrendingStockResultRepository(BaseRepository[TrendingStockResult]):
    def __init__(self, session: Session):
        super().__init__(session, TrendingStockResult)

    def get_by_run(self, run_id: str) -> list[TrendingStockResult]:
        return (
            self.session.query(TrendingStockResult)
            .filter(TrendingStockResult.discovery_run_id == run_id)
            .order_by(TrendingStockResult.trending_score.desc())
            .all()
        )

    def get_by_ticker(self, ticker: str, limit: int = 10) -> list[TrendingStockResult]:
        return (
            self.session.query(TrendingStockResult)
            .filter(TrendingStockResult.ticker == ticker)
            .order_by(TrendingStockResult.created_at.desc())
            .limit(limit)
            .all()
        )


class DiscoveryArticleRepository(BaseRepository[DiscoveryArticle]):
    def __init__(self, session: Session):
        super().__init__(session, DiscoveryArticle)

    def get_by_run(self, run_id: str) -> list[DiscoveryArticle]:
        return (
            self.session.query(DiscoveryArticle)
            .filter(DiscoveryArticle.discovery_run_id == run_id)
            .all()
        )


class DiscoveryService:
    def __init__(self, session: Session):
        self.session = session
        self.runs = DiscoveryRunRepository(session)
        self.stocks = TrendingStockResultRepository(session)
        self.articles = DiscoveryArticleRepository(session)

    def create_run(self, lookback_period: str, max_results: int) -> DiscoveryRun:
        return self.runs.create(
            {
                "lookback_period": lookback_period,
                "max_results": max_results,
                "status": "running",
            }
        )

    def save_trending_stock(
        self,
        run_id: str,
        ticker: str,
        company_name: str,
        trending_score: float,
        mention_count: int,
        sector: str,
        event_type: str,
        summary: str | None = None,
        source_articles: list[str] | None = None,
    ) -> TrendingStockResult:
        return self.stocks.create(
            {
                "discovery_run_id": run_id,
                "ticker": ticker,
                "company_name": company_name,
                "trending_score": trending_score,
                "mention_count": mention_count,
                "sector": sector,
                "event_type": event_type,
                "summary": summary,
                "source_articles": json.dumps(source_articles or []),
            }
        )

    def save_article(
        self,
        run_id: str,
        title: str,
        source: str,
        url: str | None = None,
        published_at: datetime | None = None,
        content_snippet: str | None = None,
    ) -> DiscoveryArticle:
        return self.articles.create(
            {
                "discovery_run_id": run_id,
                "title": title,
                "source": source,
                "url": url,
                "published_at": published_at,
                "content_snippet": content_snippet,
            }
        )

    def complete_run(self, run_id: str, stocks_found: int) -> DiscoveryRun | None:
        run = self.runs.get(run_id)
        if run:
            run.status = "completed"
            run.completed_at = datetime.utcnow()
            run.stocks_found = stocks_found
            self.session.flush()
        return run

    def fail_run(self, run_id: str, error: str) -> DiscoveryRun | None:
        run = self.runs.get(run_id)
        if run:
            run.status = "failed"
            run.completed_at = datetime.utcnow()
            run.error_message = error
            self.session.flush()
        return run

    def get_latest_run(self) -> DiscoveryRun | None:
        return self.runs.get_latest()

    def get_trending_by_run(self, run_id: str) -> list[TrendingStockResult]:
        return self.stocks.get_by_run(run_id)

    def get_stock_history(
        self, ticker: str, limit: int = 10
    ) -> list[TrendingStockResult]:
        return self.stocks.get_by_ticker(ticker, limit)
