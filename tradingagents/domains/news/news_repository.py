"""
Repository for historical news data (cached files and PostgreSQL).
"""

from __future__ import annotations

import builtins
import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Float,
    Index,
    String,
    Text,
    and_,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column
from uuid_utils import uuid7

from tradingagents.lib.database import Base, DatabaseManager

logger = logging.getLogger(__name__)


@dataclass
class NewsArticle:
    """Represents a news article."""

    headline: str
    url: str  # Unique identifier for deduplication
    source: str  # "Finnhub", "Google News", etc.
    published_date: date

    # Optional fields
    summary: str | None = None
    entities: list[str] = field(default_factory=list)
    sentiment_score: float | None = None
    sentiment_confidence: float | None = None  # New field
    sentiment_label: str | None = None  # New field
    author: str | None = None
    category: str | None = None

    def to_entity(self, symbol: str | None = None) -> NewsArticleEntity:
        """Convert NewsArticle dataclass to NewsArticleEntity SQLAlchemy model."""
        return NewsArticleEntity(
            headline=self.headline,
            url=self.url,
            source=self.source,
            published_date=self.published_date,
            summary=self.summary,
            entities=self.entities if self.entities else None,
            sentiment_score=self.sentiment_score,
            sentiment_confidence=self.sentiment_confidence,
            sentiment_label=self.sentiment_label,
            author=self.author,
            category=self.category,
            symbol=symbol,
        )

    @staticmethod
    def from_entity(entity: NewsArticleEntity) -> NewsArticle:
        """Convert NewsArticleEntity SQLAlchemy model to NewsArticle dataclass."""
        from typing import cast

        return NewsArticle(
            headline=cast("str", entity.headline),
            url=cast("str", entity.url),
            source=cast("str", entity.source),
            published_date=cast("date", entity.published_date),
            summary=cast("str | None", entity.summary),
            entities=cast("list[str] | None", entity.entities) or [],
            sentiment_score=cast("float | None", entity.sentiment_score),
            sentiment_confidence=cast("float | None", entity.sentiment_confidence),
            sentiment_label=cast("str | None", entity.sentiment_label),
            author=cast("str | None", entity.author),
            category=cast("str | None", entity.category),
        )

    def has_reliable_sentiment(self) -> bool:
        """
        Check if the article has reliable sentiment data.

        Returns True when sentiment_score is not None AND sentiment_confidence is not None
        AND sentiment_confidence >= 0.6

        Returns:
            bool: True if sentiment data is reliable, False otherwise
        """
        return bool(
            self.sentiment_score is not None
            and self.sentiment_confidence is not None
            and self.sentiment_confidence >= 0.6
        )


class NewsArticleEntity(Base):
    """SQLAlchemy model for news articles with vector embedding support."""

    __tablename__ = "news_articles"
    __table_args__ = (
        # Composite indexes for common query patterns
        Index("idx_symbol_date", "symbol", "published_date"),
        Index("idx_published_date", "published_date"),
        Index("idx_url_unique", "url", unique=True),
        # TimescaleDB will automatically create time-based partitions on published_date
    )

    # Primary key using UUID v7 for time-ordered identifiers
    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid7
    )

    # Core article fields (matching existing NewsArticle dataclass)
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(
        Text, nullable=False, unique=True
    )  # Used for deduplication
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    published_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # Optional fields from NewsArticle dataclass
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    entities: Mapped[list[str] | None] = mapped_column(
        JSON, nullable=True
    )  # Store list[str] as JSON array
    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    sentiment_confidence: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )  # New field
    sentiment_label: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # New field
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Symbol field for filtering (nullable for global news)
    symbol: Mapped[str | None] = mapped_column(String(20), index=True, nullable=True)

    # Vector embeddings for semantic similarity (1536 dimensions for OpenAI embeddings)
    title_embedding: Mapped[list[float] | None] = mapped_column(
        Vector(1536), nullable=True
    )
    content_embedding: Mapped[list[float] | None] = mapped_column(
        Vector(1536), nullable=True
    )

    # Audit timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<NewsArticleDB(id={self.id}, headline='{self.headline[:50]}...', source='{self.source}')>"


class NewsRepository:
    """Repository for news articles"""

    def __init__(self, database_manager: DatabaseManager):
        """
        Initialize async PostgreSQL news repository.

        Args:
            database_manager: AsyncDatabaseManager instance. If None, creates default.
        """
        self.db_manager = database_manager

    async def list(self, symbol: str, date: date) -> list[NewsArticle]:
        """
        List articles for a symbol on a specific date.

        Args:
            symbol: Stock symbol or query
            date: Date to filter articles

        Returns:
            List[NewsArticle]: Articles for the symbol and date
        """
        async with self.db_manager.get_session() as session:
            result = await session.execute(
                select(NewsArticleEntity)
                .filter(
                    and_(
                        NewsArticleEntity.symbol == symbol,
                        NewsArticleEntity.published_date == date,
                    )
                )
                .order_by(NewsArticleEntity.published_date.desc())
            )
            db_articles = result.scalars().all()

            # Convert to dataclass instances
            articles = [NewsArticle.from_entity(article) for article in db_articles]

        logger.info(f"Retrieved {len(articles)} articles for {symbol} on {date}")
        return articles

    async def get(self, article_id: uuid.UUID) -> NewsArticle | None:
        """
        Get single article by UUID.

        Args:
            article_id: UUID v7 of the article

        Returns:
            NewsArticle | None: Article if found, None otherwise
        """
        async with self.db_manager.get_session() as session:
            result = await session.execute(
                select(NewsArticleEntity).filter(NewsArticleEntity.id == article_id)
            )
            db_article = result.scalar_one_or_none()

            if db_article:
                article = NewsArticle.from_entity(db_article)
                logger.debug(f"Retrieved article {article_id}")
                return article

        logger.debug(f"Article {article_id} not found")
        return None

    async def upsert(self, article: NewsArticle, symbol: str) -> NewsArticle:
        """
        Insert or update article using URL as unique constraint.

        Args:
            article: NewsArticle to insert or update
            symbol: Optional symbol to associate with the article

        Returns:
            NewsArticle: The stored article with database metadata
        """
        from sqlalchemy.dialects.postgresql import insert

        async with self.db_manager.get_session() as session:
            try:
                # Convert to entity and prepare data for insert
                entity_data = {
                    "headline": article.headline,
                    "url": article.url,
                    "source": article.source,
                    "published_date": article.published_date,
                    "summary": article.summary,
                    "entities": article.entities if article.entities else None,
                    "sentiment_score": article.sentiment_score,
                    "sentiment_confidence": article.sentiment_confidence,
                    "sentiment_label": article.sentiment_label,
                    "author": article.author,
                    "category": article.category,
                    "symbol": symbol,
                }

                # Use PostgreSQL INSERT ON CONFLICT for atomic upsert
                stmt = insert(NewsArticleEntity).values(**entity_data)
                upsert_stmt = stmt.on_conflict_do_update(
                    index_elements=["url"],
                    set_={
                        "headline": stmt.excluded.headline,
                        "source": stmt.excluded.source,
                        "published_date": stmt.excluded.published_date,
                        "summary": stmt.excluded.summary,
                        "entities": stmt.excluded.entities,
                        "sentiment_score": stmt.excluded.sentiment_score,
                        "sentiment_confidence": stmt.excluded.sentiment_confidence,
                        "sentiment_label": stmt.excluded.sentiment_label,
                        "author": stmt.excluded.author,
                        "category": stmt.excluded.category,
                        "symbol": stmt.excluded.symbol,
                        "updated_at": func.now(),
                    },
                ).returning(NewsArticleEntity)

                result = await session.execute(upsert_stmt)
                db_article = result.scalar_one()
                result_article = NewsArticle.from_entity(db_article)

                logger.info(f"Upserted article: {article.url}")
                return result_article

            except IntegrityError as e:
                await session.rollback()
                logger.error(
                    f"Database integrity error upserting article {article.url}: {e}"
                )
                raise
            except Exception as e:
                await session.rollback()
                logger.error(f"Error upserting article {article.url}: {e}")
                raise

    async def delete(self, article_id: uuid.UUID) -> bool:
        """
        Delete article by UUID.

        Args:
            article_id: UUID v7 of the article to delete

        Returns:
            bool: True if deleted, False if not found
        """

        async with self.db_manager.get_session() as session:
            result = await session.execute(
                select(NewsArticleEntity).filter(NewsArticleEntity.id == article_id)
            )
            db_article = result.scalar_one_or_none()

            if db_article:
                await session.delete(db_article)
                logger.info(f"Deleted article {article_id}")
                return True

        logger.debug(f"Article {article_id} not found for deletion")
        return False

    async def list_by_date_range(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        limit: int = 100,
    ) -> builtins.list[NewsArticle]:
        """
        List articles by date range, optionally filtered by symbol.

        Args:
            symbol: Optional symbol filter
            start_date: Optional start date
            end_date: Optional end date
            limit: Maximum number of articles to return

        Returns:
            List[NewsArticle]: Articles matching the criteria
        """
        async with self.db_manager.get_session() as session:
            query = select(NewsArticleEntity)

            # Apply filters
            filters = []
            if symbol:
                filters.append(NewsArticleEntity.symbol == symbol)
            if start_date:
                filters.append(NewsArticleEntity.published_date >= start_date)
            if end_date:
                filters.append(NewsArticleEntity.published_date <= end_date)

            if filters:
                query = query.filter(and_(*filters))

            # Order by date descending and limit
            query = query.order_by(NewsArticleEntity.published_date.desc()).limit(limit)

            result = await session.execute(query)
            db_articles = result.scalars().all()

            articles = [
                NewsArticle.from_entity(db_article) for db_article in db_articles
            ]

        logger.info(f"Retrieved {len(articles)} articles for date range query")
        return articles

    async def upsert_batch(
        self, articles: builtins.list[NewsArticle], symbol: str
    ) -> builtins.list[NewsArticle]:
        """
        Batch insert or update articles using bulk SQL operations.

        Args:
            articles: List of NewsArticle objects to store
            symbol: Symbol to associate with all articles

        Returns:
            List[NewsArticle]: The stored articles with database metadata
        """
        from sqlalchemy.dialects.postgresql import insert

        if not articles:
            return []

        async with self.db_manager.get_session() as session:
            try:
                # Prepare data for bulk insert
                entity_data_list = [
                    {
                        "headline": article.headline,
                        "url": article.url,
                        "source": article.source,
                        "published_date": article.published_date,
                        "summary": article.summary,
                        "entities": article.entities if article.entities else None,
                        "sentiment_score": article.sentiment_score,
                        "sentiment_confidence": article.sentiment_confidence,
                        "sentiment_label": article.sentiment_label,
                        "author": article.author,
                        "category": article.category,
                        "symbol": symbol,
                    }
                    for article in articles
                ]

                # Use PostgreSQL bulk INSERT ON CONFLICT for atomic batch upsert
                stmt = insert(NewsArticleEntity).values(entity_data_list)
                upsert_stmt = stmt.on_conflict_do_update(
                    index_elements=["url"],
                    set_={
                        "headline": stmt.excluded.headline,
                        "source": stmt.excluded.source,
                        "published_date": stmt.excluded.published_date,
                        "summary": stmt.excluded.summary,
                        "entities": stmt.excluded.entities,
                        "sentiment_score": stmt.excluded.sentiment_score,
                        "sentiment_confidence": stmt.excluded.sentiment_confidence,
                        "sentiment_label": stmt.excluded.sentiment_label,
                        "author": stmt.excluded.author,
                        "category": stmt.excluded.category,
                        "symbol": stmt.excluded.symbol,
                        "updated_at": func.now(),
                    },
                ).returning(NewsArticleEntity)

                result = await session.execute(upsert_stmt)
                db_articles = result.scalars().all()
                stored_articles = [
                    NewsArticle.from_entity(db_article) for db_article in db_articles
                ]

                logger.info(
                    f"Batch upserted {len(stored_articles)} articles for {symbol}"
                )
                return stored_articles

            except IntegrityError as e:
                await session.rollback()
                logger.error(
                    f"Database integrity error during batch upsert for {symbol}: {e}"
                )
                raise
            except Exception as e:
                await session.rollback()
                logger.error(f"Error during batch upsert for {symbol}: {e}")
                raise
