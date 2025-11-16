"""
Tests for Dagster operations with real OpenRouter integration.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timezone

from dagster import build_op_context
from tradingagents.workflows.ops import fetch_and_process_article
from tradingagents.domains.news.openrouter_client import SentimentResult


class TestDagsterOpenRouterIntegration:
    """Test integration between Dagster ops and OpenRouter LLM clients."""

    @pytest.fixture
    def mock_context(self):
        """Mock Dagster operation context."""
        context = build_op_context()
        return context

    @pytest.fixture
    def sample_article_data(self):
        """Sample article data for testing."""
        return {
            "index": 0,
            "ticker": "AAPL",
            "title": "Apple Reports Strong Q4 Earnings",
            "url": "https://example.com/apple-earnings",
            "source": "Reuters",
            "published_date": "2025-01-15",
            "summary": "Apple beats expectations with strong iPhone sales.",
        }

    @patch('tradingagents.workflows.ops.NewsService.build')
    @patch('tradingagents.workflows.ops.asyncio.run')
    def test_fetch_and_process_article_uses_real_openrouter_sentiment(
        self, mock_asyncio_run, mock_news_service_build, mock_context, sample_article_data
    ):
        """Test that fetch_and_process_article uses real OpenRouter sentiment analysis."""
        
        # Mock NewsService and its components
        mock_news_service = Mock()
        mock_scraper = Mock()
        mock_openrouter_client = Mock()
        mock_repository = AsyncMock()
        
        # Configure mock scraper
        mock_scrape_result = Mock()
        mock_scrape_result.status = "SUCCESS"
        mock_scrape_result.content = "Apple reported strong quarterly earnings..."
        mock_scrape_result.author = "John Doe"
        mock_scrape_result.publish_date = "2025-01-15"
        mock_scraper.scrape_article.return_value = mock_scrape_result
        
        # Configure mock OpenRouter client
        mock_sentiment_result = SentimentResult(
            sentiment="positive",
            confidence=0.85,
            reasoning="Strong earnings beat expectations"
        )
        mock_openrouter_client.analyze_sentiment.return_value = mock_sentiment_result
        mock_openrouter_client.create_embedding.return_value = [0.1] * 1536
        
        # Configure mock NewsService
        mock_news_service.article_scraper = mock_scraper
        mock_news_service._openrouter_client = mock_openrouter_client
        mock_news_service.repository = mock_repository
        mock_news_service_build.return_value = mock_news_service
        
        # Mock asyncio.run to prevent actual async execution
        mock_asyncio_run.return_value = None
        
        # Execute the operation
        result = fetch_and_process_article(mock_context, sample_article_data)
        
        # Verify OpenRouter sentiment analysis was called
        mock_openrouter_client.analyze_sentiment.assert_called_once()
        call_args = mock_openrouter_client.analyze_sentiment.call_args[0][0]
        assert "Apple reported strong quarterly earnings" in call_args
        
        # Verify sentiment result is included in output
        assert result["sentiment"]["sentiment"] == "positive"
        assert result["sentiment"]["confidence"] == 0.85
        assert "Strong earnings beat expectations" in result["sentiment"]["reasoning"]

    @patch('tradingagents.workflows.ops.NewsService.build')
    @patch('tradingagents.workflows.ops.asyncio.run')
    def test_fetch_and_process_article_uses_real_openrouter_embeddings(
        self, mock_asyncio_run, mock_news_service_build, mock_context, sample_article_data
    ):
        """Test that fetch_and_process_article uses real OpenRouter embeddings."""
        
        # Mock NewsService and its components
        mock_news_service = Mock()
        mock_scraper = Mock()
        mock_openrouter_client = Mock()
        mock_repository = AsyncMock()
        
        # Configure mock scraper
        mock_scrape_result = Mock()
        mock_scrape_result.status = "SUCCESS"
        mock_scrape_result.content = "Apple reported strong quarterly earnings..."
        mock_scrape_result.author = "John Doe"
        mock_scrape_result.publish_date = "2025-01-15"
        mock_scraper.scrape_article.return_value = mock_scrape_result
        
        # Configure mock OpenRouter client
        mock_sentiment_result = SentimentResult(
            sentiment="positive",
            confidence=0.85,
            reasoning="Strong earnings beat expectations"
        )
        mock_openrouter_client.analyze_sentiment.return_value = mock_sentiment_result
        
        # Mock embeddings with different vectors for title and content
        title_embedding = [0.1] * 1536
        content_embedding = [0.2] * 1536
        mock_openrouter_client.create_embedding.side_effect = [
            title_embedding,  # First call for title
            content_embedding  # Second call for content
        ]
        
        # Configure mock NewsService
        mock_news_service.article_scraper = mock_scraper
        mock_news_service._openrouter_client = mock_openrouter_client
        mock_news_service.repository = mock_repository
        mock_news_service_build.return_value = mock_news_service
        
        # Mock asyncio.run to prevent actual async execution
        mock_asyncio_run.return_value = None
        
        # Execute the operation
        result = fetch_and_process_article(mock_context, sample_article_data)
        
        # Verify OpenRouter embeddings were called twice (title and content)
        assert mock_openrouter_client.create_embedding.call_count == 2
        
        # Verify embeddings are included in output
        assert result["vectors"]["title_embedding"] == title_embedding
        assert result["vectors"]["content_embedding"] == content_embedding
        assert result["vectors"]["embedding_model"] == "text-embedding-3-small"
        assert result["vectors"]["embedding_dimensions"] == 1536

    @patch('tradingagents.workflows.ops.NewsService.build')
    @patch('tradingagents.workflows.ops.asyncio.run')
    def test_fetch_and_process_article_stores_sentiment_and_embeddings_in_database(
        self, mock_asyncio_run, mock_news_service_build, mock_context, sample_article_data
    ):
        """Test that sentiment and embeddings are properly formatted for database storage."""
        
        # Mock NewsService and its components
        mock_news_service = Mock()
        mock_scraper = Mock()
        mock_openrouter_client = Mock()
        mock_repository = AsyncMock()
        
        # Configure mock scraper
        mock_scrape_result = Mock()
        mock_scrape_result.status = "SUCCESS"
        mock_scrape_result.content = "Apple reported strong quarterly earnings..."
        mock_scrape_result.author = "John Doe"
        mock_scrape_result.publish_date = "2025-01-15"
        mock_scraper.scrape_article.return_value = mock_scrape_result
        
        # Configure mock OpenRouter client
        mock_sentiment_result = SentimentResult(
            sentiment="positive",
            confidence=0.85,
            reasoning="Strong earnings beat expectations"
        )
        mock_openrouter_client.analyze_sentiment.return_value = mock_sentiment_result
        mock_openrouter_client.create_embedding.return_value = [0.1] * 1536
        
        # Configure mock NewsService
        mock_news_service.article_scraper = mock_scraper
        mock_news_service._openrouter_client = mock_openrouter_client
        mock_news_service.repository = mock_repository
        mock_news_service_build.return_value = mock_news_service
        
        # Mock asyncio.run to prevent actual async execution
        mock_asyncio_run.return_value = None
        
        # Execute the operation
        result = fetch_and_process_article(mock_context, sample_article_data)
        
        # Verify the operation completed successfully
        assert result["scrape_status"] == "SUCCESS"
        assert result["sentiment"]["sentiment"] == "positive"
        assert result["sentiment"]["confidence"] == 0.85
        assert result["vectors"]["title_embedding"] == [0.1] * 1536
        assert result["vectors"]["content_embedding"] == [0.1] * 1536
        
        # Verify that the sentiment and embedding data is properly formatted for storage
        # The actual database storage is handled by the async function, but we can 
        # verify the data is correctly structured in the result
        assert "storage_status" in result
        assert result["storage_status"] in ["success", "error"]

    @patch('tradingagents.workflows.ops.NewsService.build')
    def test_fetch_and_process_article_handles_openrouter_failures_gracefully(
        self, mock_news_service_build, mock_context, sample_article_data
    ):
        """Test that OpenRouter failures don't break the entire pipeline."""
        
        # Mock NewsService and its components
        mock_news_service = Mock()
        mock_scraper = Mock()
        mock_openrouter_client = Mock()
        mock_repository = AsyncMock()
        
        # Configure mock scraper
        mock_scrape_result = Mock()
        mock_scrape_result.status = "SUCCESS"
        mock_scrape_result.content = "Apple reported strong quarterly earnings..."
        mock_scrape_result.author = "John Doe"
        mock_scrape_result.publish_date = "2025-01-15"
        mock_scraper.scrape_article.return_value = mock_scrape_result
        
        # Configure mock OpenRouter client to fail
        mock_openrouter_client.analyze_sentiment.side_effect = Exception("API Error")
        mock_openrouter_client.create_embedding.side_effect = Exception("API Error")
        
        # Configure mock NewsService
        mock_news_service.article_scraper = mock_scraper
        mock_news_service._openrouter_client = mock_openrouter_client
        mock_news_service.repository = mock_repository
        mock_news_service_build.return_value = mock_news_service
        
        # Mock asyncio.run to prevent actual async execution
        with patch('tradingagents.workflows.ops.asyncio.run') as mock_asyncio:
            mock_asyncio.return_value = None
            
            # Execute the operation
            result = fetch_and_process_article(mock_context, sample_article_data)
            
            # Operation should still complete despite OpenRouter failures
            assert result["scrape_status"] == "SUCCESS"
            assert result["content"] == "Apple reported strong quarterly earnings..."
            
            # Should have error information in sentiment and vectors
            assert result["sentiment"]["sentiment"] == "neutral"
            assert result["sentiment"]["confidence"] == 0.0
            assert "Analysis failed:" in result["sentiment"]["reasoning"]
            
            # Should have zero vectors as fallback
            assert result["vectors"]["title_embedding"] == [0.0] * 1536
            assert result["vectors"]["content_embedding"] == [0.0] * 1536
            assert "error" in result["vectors"]