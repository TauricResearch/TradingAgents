"""
Integration tests for NewsRepository.

Tests the PostgreSQL repository with TimescaleDB using Docker.
Follows pragmatic TDD principles - test real persistence with Docker container.
"""

import asyncio
from datetime import date

import pytest
from sqlalchemy import text
from uuid_utils import uuid7

from tradingagents.domains.news.news_repository import (
    NewsArticle,
    NewsArticleEntity,
    NewsRepository,
)
from tradingagents.lib.database import create_test_database_manager


@pytest.fixture
async def test_db_manager():
    """Create test database manager with TimescaleDB container."""
    db_manager = create_test_database_manager()

    # Verify database health
    health = await db_manager.health_check()
    if not health:
        pytest.skip("TimescaleDB test container not available")

    # Create tables
    await db_manager.create_tables()

    yield db_manager

    # Cleanup
    await db_manager.drop_tables()
    await db_manager.close()


@pytest.fixture
async def repository(test_db_manager):
    """Create repository instance with test database."""
    repo = NewsRepository(test_db_manager)

    # Clean up any existing test data
    async with test_db_manager.get_session() as session:
        await session.execute(text("DELETE FROM news_articles"))
        await session.commit()

    return repo


@pytest.fixture
def sample_article():
    """Create a sample news article for testing."""
    return NewsArticle(
        headline="Apple Quarterly Earnings Beat Expectations",
        url="https://example.com/apple-earnings-q1-2024",
        source="TechCrunch",
        published_date=date(2024, 1, 15),
        summary="Apple reported strong quarterly earnings with iPhone sales exceeding analyst predictions.",
        entities=["Apple", "iPhone", "earnings"],
        sentiment_score=0.8,
        author="Jane Tech Reporter",
        category="earnings",
    )


@pytest.fixture
def another_sample_article():
    """Create another sample news article for testing."""
    return NewsArticle(
        headline="Tesla Stock Drops After Production Concerns",
        url="https://example.com/tesla-stock-drop-2024",
        source="Bloomberg",
        published_date=date(2024, 1, 16),
        summary="Tesla shares fell following reports of production line issues.",
        entities=["Tesla", "stock", "production"],
        sentiment_score=-0.3,
        author="Financial Reporter",
        category="stock-news",
    )


class TestNewsRepository:
    """Test suite for NewsRepository."""

    async def test_upsert_new_article(self, repository, sample_article):
        """Test inserting a new article."""
        # Act
        result = await repository.upsert(sample_article, symbol="AAPL")

        # Assert
        assert result.headline == sample_article.headline
        assert result.url == sample_article.url
        assert result.source == sample_article.source
        assert result.published_date == sample_article.published_date
        assert result.summary == sample_article.summary
        assert result.entities == sample_article.entities
        assert result.sentiment_score == sample_article.sentiment_score
        assert result.author == sample_article.author
        assert result.category == sample_article.category

    async def test_upsert_duplicate_url_updates_existing(
        self, repository, sample_article
    ):
        """Test that upserting an article with existing URL updates the existing record."""
        # Arrange - Insert initial article
        await repository.upsert(sample_article, symbol="AAPL")

        # Modify the article content
        updated_article = NewsArticle(
            headline="UPDATED: Apple Quarterly Earnings Exceed All Expectations",
            url=sample_article.url,  # Same URL
            source="Updated TechCrunch",
            published_date=sample_article.published_date,
            summary="Updated summary with more details.",
            entities=["Apple", "iPhone", "earnings", "record"],
            sentiment_score=0.9,
            author="Senior Tech Reporter",
            category="earnings-updated",
        )

        # Act
        result = await repository.upsert(updated_article, symbol="AAPL")

        # Assert - Should be updated, not duplicated
        assert (
            result.headline
            == "UPDATED: Apple Quarterly Earnings Exceed All Expectations"
        )
        assert result.source == "Updated TechCrunch"
        assert result.summary == "Updated summary with more details."
        assert result.sentiment_score == 0.9
        assert result.author == "Senior Tech Reporter"
        assert result.category == "earnings-updated"
        assert len(result.entities) == 4

    async def test_get_by_uuid(self, repository, sample_article):
        """Test retrieving an article by its UUID."""
        # Arrange
        await repository.upsert(sample_article, symbol="AAPL")

        # We need to get the UUID from the database since it's auto-generated
        stored_uuid = None

        # Get UUID from the database model
        async with repository.db_manager.get_session() as session:
            from sqlalchemy import select

            result = await session.execute(
                select(NewsArticleEntity).filter(
                    NewsArticleEntity.url == sample_article.url
                )
            )
            db_article = result.scalar_one()
            stored_uuid = db_article.id

        # Act
        retrieved_article = await repository.get(stored_uuid)

        # Assert
        assert retrieved_article is not None
        assert retrieved_article.headline == sample_article.headline
        assert retrieved_article.url == sample_article.url

    async def test_get_nonexistent_uuid_returns_none(self, repository):
        """Test that getting a non-existent UUID returns None."""
        # Arrange
        fake_uuid = uuid7()

        # Act
        result = await repository.get(fake_uuid)

        # Assert
        assert result is None

    async def test_list_articles_by_symbol_and_date(
        self, repository, sample_article, another_sample_article
    ):
        """Test listing articles filtered by symbol and date."""
        # Arrange
        await repository.upsert(sample_article, symbol="AAPL")
        await repository.upsert(another_sample_article, symbol="TSLA")

        # Act - Get AAPL articles for Jan 15, 2024
        aapl_articles = await repository.list("AAPL", date(2024, 1, 15))
        tsla_articles = await repository.list("TSLA", date(2024, 1, 16))
        no_articles = await repository.list("AAPL", date(2024, 1, 16))  # Wrong date

        # Assert
        assert len(aapl_articles) == 1
        assert aapl_articles[0].headline == sample_article.headline

        assert len(tsla_articles) == 1
        assert tsla_articles[0].headline == another_sample_article.headline

        assert len(no_articles) == 0

    async def test_delete_article_by_uuid(self, repository, sample_article):
        """Test deleting an article by UUID."""
        # Arrange
        await repository.upsert(sample_article, symbol="AAPL")

        # Get the UUID
        async with repository.db_manager.get_session() as session:
            from sqlalchemy import select

            result = await session.execute(
                select(NewsArticleEntity).filter(
                    NewsArticleEntity.url == sample_article.url
                )
            )
            db_article = result.scalar_one()
            article_uuid = db_article.id

        # Act
        deleted = await repository.delete(article_uuid)

        # Assert
        assert deleted is True

        # Verify article is gone
        retrieved = await repository.get(article_uuid)
        assert retrieved is None

    async def test_delete_nonexistent_uuid_returns_false(self, repository):
        """Test that deleting a non-existent UUID returns False."""
        # Arrange
        fake_uuid = uuid7()

        # Act
        result = await repository.delete(fake_uuid)

        # Assert
        assert result is False

    async def test_list_by_date_range_with_filters(
        self, repository, sample_article, another_sample_article
    ):
        """Test listing articles by date range with optional filters."""
        # Arrange
        await repository.upsert(sample_article, symbol="AAPL")
        await repository.upsert(another_sample_article, symbol="TSLA")

        # Act - Various filter combinations
        all_articles_aapl = await repository.list_by_date_range(
            symbol="AAPL",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            limit=10,
        )

        all_articles_tsla = await repository.list_by_date_range(
            symbol="TSLA",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            limit=10,
        )

        aapl_only = await repository.list_by_date_range(
            symbol="AAPL", start_date=date(2024, 1, 1), end_date=date(2024, 1, 31)
        )

        date_filtered = await repository.list_by_date_range(
            symbol="TSLA", start_date=date(2024, 1, 16), end_date=date(2024, 1, 16)
        )

        # Assert
        assert len(all_articles_aapl) == 1
        assert len(all_articles_tsla) == 1
        assert len(aapl_only) == 1
        assert aapl_only[0].headline == sample_article.headline
        assert len(date_filtered) == 1
        assert date_filtered[0].headline == another_sample_article.headline

    async def test_uuid_v7_ordering(self, repository):
        """Test that UUID v7 provides time-ordered identifiers."""
        # Arrange - Create articles with slight time differences
        article1 = NewsArticle(
            headline="First Article",
            url="https://example.com/first",
            source="Test Source",
            published_date=date(2024, 1, 15),
        )

        article2 = NewsArticle(
            headline="Second Article",
            url="https://example.com/second",
            source="Test Source",
            published_date=date(2024, 1, 15),
        )

        # Act - Insert articles
        await repository.upsert(article1, symbol="TEST")
        # Small delay to ensure different timestamps
        await asyncio.sleep(0.001)
        await repository.upsert(article2, symbol="TEST")

        # Get UUIDs in creation order
        async with repository.db_manager.get_session() as session:
            from sqlalchemy import select

            result = await session.execute(
                select(NewsArticleEntity.id, NewsArticleEntity.headline)
                .filter(NewsArticleEntity.symbol == "TEST")
                .order_by(NewsArticleEntity.created_at)
            )
            articles = result.all()

        # Assert - UUID v7 should be time-ordered (first UUID < second UUID)
        assert len(articles) == 2
        first_uuid = articles[0].id
        second_uuid = articles[1].id

        # UUID v7 has timestamp in the first part, so earlier UUIDs are "smaller"
        assert first_uuid < second_uuid

    async def test_database_schema_validation(self, repository, sample_article):
        """Test that the database schema correctly handles all field types."""
        # Arrange - Article with all field types
        complex_article = NewsArticle(
            headline="Complex Test Article with All Fields",
            url="https://example.com/complex-test",
            source="Test Source",
            published_date=date(2024, 1, 15),
            summary="This is a test summary with unicode characters: ñáéíóú",
            entities=["Entity1", "Entity2", "Special-Entity_123"],
            sentiment_score=0.756789,  # Test float precision
            author="Test Author with Accents: José María",
            category="test-category-123",
        )

        # Act
        await repository.upsert(complex_article, symbol="TEST")
        retrieved = await repository.list("TEST", date(2024, 1, 15))

        # Assert - All data preserved correctly
        article = retrieved[0]
        assert article.headline == complex_article.headline
        assert article.summary == complex_article.summary
        assert article.entities == complex_article.entities
        assert abs(article.sentiment_score - complex_article.sentiment_score) < 0.000001
        assert article.author == complex_article.author
        assert article.category == complex_article.category

    async def test_upsert_batch_performance(self, repository):
        """Test that upsert_batch handles multiple articles efficiently."""
        # Arrange - Create multiple test articles
        articles = [
            NewsArticle(
                headline=f"Test Article {i}",
                url=f"https://example.com/test-{i}",
                source="Batch Test Source",
                published_date=date(2024, 1, 15),
                summary=f"Summary for article {i}",
                entities=[f"Entity{i}"],
                sentiment_score=0.5 + (i * 0.1),
                author=f"Author {i}",
                category="batch-test",
            )
            for i in range(5)
        ]

        # Act - Batch upsert
        stored_articles = await repository.upsert_batch(articles, symbol="BATCH")

        # Assert - All articles stored correctly
        assert len(stored_articles) == 5
        for i, stored in enumerate(stored_articles):
            assert stored.headline == f"Test Article {i}"
            assert stored.url == f"https://example.com/test-{i}"
            assert stored.source == "Batch Test Source"

        # Verify articles can be retrieved individually
        retrieved_articles = await repository.list("BATCH", date(2024, 1, 15))
        assert len(retrieved_articles) == 5

    async def test_upsert_batch_empty_list(self, repository):
        """Test that upsert_batch handles empty list gracefully."""
        # Act
        result = await repository.upsert_batch([], symbol="EMPTY")

        # Assert
        assert result == []


class TestNewsArticleSentimentFields:
    """Test suite for new sentiment fields in NewsArticle."""

    def test_news_article_with_sentiment_fields(self):
        """Test dataclass instantiation with new sentiment fields."""
        # Arrange & Act
        article = NewsArticle(
            headline="Test Article",
            url="https://example.com/test",
            source="Test Source",
            published_date=date(2024, 1, 15),
            sentiment_score=0.8,
            sentiment_confidence=0.95,
            sentiment_label="positive",
        )

        # Assert
        assert article.sentiment_score == 0.8
        assert article.sentiment_confidence == 0.95
        assert article.sentiment_label == "positive"

    async def test_news_article_to_entity_includes_sentiment_fields(
        self, test_db_manager
    ):
        """Test to_entity() maps new sentiment fields correctly."""
        # Arrange
        article = NewsArticle(
            headline="Test Article",
            url="https://example.com/test",
            source="Test Source",
            published_date=date(2024, 1, 15),
            sentiment_score=0.75,
            sentiment_confidence=0.88,
            sentiment_label="positive",
        )

        # Act
        entity = article.to_entity(symbol="TEST")

        # Assert
        assert entity.sentiment_score == 0.75
        assert entity.sentiment_confidence == 0.88
        assert entity.sentiment_label == "positive"

    async def test_news_article_from_entity_includes_sentiment_fields(self, repository):
        """Test from_entity() populates new sentiment fields correctly."""
        # Arrange - Create an article with sentiment fields
        article = NewsArticle(
            headline="Test Article",
            url="https://example.com/test-from-entity",
            source="Test Source",
            published_date=date(2024, 1, 15),
            sentiment_score=0.65,
            sentiment_confidence=0.92,
            sentiment_label="negative",
        )

        # Act - Store and retrieve
        await repository.upsert(article, symbol="TEST")
        retrieved_articles = await repository.list("TEST", date(2024, 1, 15))

        # Assert
        assert len(retrieved_articles) == 1
        retrieved = retrieved_articles[0]
        assert retrieved.sentiment_score == 0.65
        assert retrieved.sentiment_confidence == 0.92
        assert retrieved.sentiment_label == "negative"

    def test_has_reliable_sentiment_with_valid_confidence(self):
        """Test has_reliable_sentiment() returns True when confidence >= 0.6."""
        # Arrange
        article = NewsArticle(
            headline="Test Article",
            url="https://example.com/test",
            source="Test Source",
            published_date=date(2024, 1, 15),
            sentiment_score=0.8,
            sentiment_confidence=0.6,  # Exactly at threshold
        )

        # Act & Assert
        assert article.has_reliable_sentiment() is True

        # Test with higher confidence
        article.sentiment_confidence = 0.95
        assert article.has_reliable_sentiment() is True

    def test_has_reliable_sentiment_with_low_confidence(self):
        """Test has_reliable_sentiment() returns False when confidence < 0.6."""
        # Arrange
        article = NewsArticle(
            headline="Test Article",
            url="https://example.com/test",
            source="Test Source",
            published_date=date(2024, 1, 15),
            sentiment_score=0.8,
            sentiment_confidence=0.59,  # Just below threshold
        )

        # Act & Assert
        assert article.has_reliable_sentiment() is False

        # Test with very low confidence
        article.sentiment_confidence = 0.1
        assert article.has_reliable_sentiment() is False

    def test_has_reliable_sentiment_with_none_values(self):
        """Test has_reliable_sentiment() returns False when fields are None."""
        # Arrange - Article with no sentiment data
        article = NewsArticle(
            headline="Test Article",
            url="https://example.com/test",
            source="Test Source",
            published_date=date(2024, 1, 15),
        )

        # Act & Assert
        assert article.has_reliable_sentiment() is False

        # Test with only sentiment_score
        article.sentiment_score = 0.8
        assert article.has_reliable_sentiment() is False

        # Test with only sentiment_confidence
        article.sentiment_score = None
        article.sentiment_confidence = 0.9
        assert article.has_reliable_sentiment() is False

    async def test_news_article_roundtrip_conversion(self, repository):
        """Test to_entity() → from_entity() preserves all fields including new sentiment fields."""
        # Arrange - Create article with all fields including new sentiment fields
        original = NewsArticle(
            headline="Roundtrip Test Article",
            url="https://example.com/roundtrip-test",
            source="Test Source",
            published_date=date(2024, 1, 15),
            summary="Test summary",
            entities=["Entity1", "Entity2"],
            sentiment_score=0.72,
            sentiment_confidence=0.87,
            sentiment_label="neutral",
            author="Test Author",
            category="test-category",
        )

        # Act - Store and retrieve (full roundtrip)
        await repository.upsert(original, symbol="TEST")
        retrieved_articles = await repository.list("TEST", date(2024, 1, 15))

        # Assert - All fields preserved
        assert len(retrieved_articles) == 1
        retrieved = retrieved_articles[0]

        assert retrieved.headline == original.headline
        assert retrieved.url == original.url
        assert retrieved.source == original.source
        assert retrieved.published_date == original.published_date
        assert retrieved.summary == original.summary
        assert retrieved.entities == original.entities
        assert retrieved.sentiment_score == original.sentiment_score
        assert retrieved.sentiment_confidence == original.sentiment_confidence
        assert retrieved.sentiment_label == original.sentiment_label
        assert retrieved.author == original.author
        assert retrieved.category == original.category


class TestDatabaseConnectionManagement:
    """Test database connection and session management."""

    async def test_database_health_check(self, test_db_manager):
        """Test database health check functionality."""
        # Act
        health = await test_db_manager.health_check()

        # Assert
        assert health is True

    async def test_session_context_manager(self, test_db_manager):
        """Test that session context manager handles transactions correctly."""
        # Act & Assert - No exceptions should be raised
        async with test_db_manager.get_session() as session:
            await session.execute(text("SELECT 1"))
            # Session should auto-commit on successful exit

    async def test_session_rollback_on_exception(self, test_db_manager):
        """Test that session rolls back on exceptions."""
        with pytest.raises(Exception, match="Test exception"):
            async with test_db_manager.get_session() as session:
                await session.execute(text("SELECT 1"))
                raise Exception("Test exception")
                # Session should auto-rollback due to exception
