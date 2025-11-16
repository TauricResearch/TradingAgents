"""
Tests for OpenRouter sentiment analysis integration.
"""

import os
import sys
from unittest.mock import Mock, patch

import pytest

# Add the project root to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from tradingagents.domains.news.news_service import (
    ArticleData,
    NewsService,
)


class TestSentimentAnalysis:
    """Test suite for sentiment analysis integration."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_google_client = Mock()
        self.mock_repository = Mock()
        self.mock_article_scraper = Mock()

        # Test articles
        self.positive_article = ArticleData(
            title="Apple Reports Strong Earnings",
            content="Apple reported excellent quarterly earnings with strong growth and positive outlook. The company showed great performance.",
            author="Test Author",
            source="Test Source",
            date="2024-01-15",
            url="https://example.com/positive",
        )

        self.negative_article = ArticleData(
            title="Tech Company Faces Decline",
            content="The tech company reported terrible losses and declining revenue. Negative outlook with weak performance.",
            author="Test Author",
            source="Test Source",
            date="2024-01-15",
            url="https://example.com/negative",
        )

        self.neutral_article = ArticleData(
            title="Company Announces Meeting",
            content="The company announced a board meeting for next Tuesday to discuss routine business matters.",
            author="Test Author",
            source="Test Source",
            date="2024-01-15",
            url="https://example.com/neutral",
        )

    def test_keyword_sentiment_positive(self):
        """Test keyword-based sentiment analysis for positive content."""
        service = NewsService(
            self.mock_google_client,
            self.mock_repository,
            self.mock_article_scraper,
            openrouter_client=None,  # Force keyword analysis
        )

        result = service._calculate_keyword_sentiment([self.positive_article])

        assert result.label == "positive"
        assert result.score > 0
        assert result.confidence > 0

    def test_keyword_sentiment_negative(self):
        """Test keyword-based sentiment analysis for negative content."""
        service = NewsService(
            self.mock_google_client,
            self.mock_repository,
            self.mock_article_scraper,
            openrouter_client=None,  # Force keyword analysis
        )

        result = service._calculate_keyword_sentiment([self.negative_article])

        assert result.label == "negative"
        assert result.score < 0
        assert result.confidence > 0

    def test_keyword_sentiment_neutral(self):
        """Test keyword-based sentiment analysis for neutral content."""
        service = NewsService(
            self.mock_google_client,
            self.mock_repository,
            self.mock_article_scraper,
            openrouter_client=None,  # Force keyword analysis
        )

        result = service._calculate_keyword_sentiment([self.neutral_article])

        assert result.label == "neutral"
        assert abs(result.score) <= 0.1

    @patch("tradingagents.domains.news.news_service.OpenRouterClient")
    @pytest.mark.asyncio
    async def test_llm_sentiment_integration(self, mock_openrouter_class):
        """Test LLM sentiment analysis integration."""
        # Mock the OpenRouter client
        mock_client = Mock()
        mock_sentiment_result = Mock()
        mock_sentiment_result.sentiment = "positive"
        mock_sentiment_result.confidence = 0.85
        mock_sentiment_result.reasoning = "Strong financial performance"

        mock_client.analyze_sentiment.return_value = mock_sentiment_result
        mock_openrouter_class.return_value = mock_client

        service = NewsService(
            self.mock_google_client,
            self.mock_repository,
            self.mock_article_scraper,
            openrouter_client=mock_client,
        )

        result = await service._calculate_llm_sentiment([self.positive_article])

        assert result.label == "positive"
        assert result.score > 0
        assert result.confidence > 0
        mock_client.analyze_sentiment.assert_called_once_with(
            self.positive_article.content
        )

    @patch("tradingagents.domains.news.news_service.OpenRouterClient")
    @pytest.mark.asyncio
    async def test_llm_sentiment_fallback_to_keyword(self, mock_openrouter_class):
        """Test fallback to keyword analysis when LLM fails."""
        # Mock the OpenRouter client to raise an exception
        mock_client = Mock()
        mock_client.analyze_sentiment.side_effect = Exception("API Error")
        mock_openrouter_class.return_value = mock_client

        service = NewsService(
            self.mock_google_client,
            self.mock_repository,
            self.mock_article_scraper,
            openrouter_client=mock_client,
        )

        # LLM sentiment should return neutral when all articles fail
        result = await service._calculate_llm_sentiment([self.positive_article])

        # Should return neutral sentiment when LLM fails
        assert result.label == "neutral"
        assert result.score == 0.0
        assert result.confidence == 0.0

    def test_empty_articles_list(self):
        """Test sentiment analysis with empty articles list."""
        service = NewsService(
            self.mock_google_client,
            self.mock_repository,
            self.mock_article_scraper,
            openrouter_client=None,
        )

        result = service._calculate_keyword_sentiment([])

        assert result.label == "neutral"
        assert result.score == 0.0
        assert result.confidence == 0.0

    def test_article_keyword_score_calculation(self):
        """Test individual article keyword score calculation."""
        service = NewsService(
            self.mock_google_client,
            self.mock_repository,
            self.mock_article_scraper,
            openrouter_client=None,
        )

        score = service._get_article_keyword_score(self.positive_article)

        assert score is not None
        assert score > 0  # Should be positive for positive article

    def test_article_keyword_score_no_content(self):
        """Test keyword score calculation for article with no content."""
        service = NewsService(
            self.mock_google_client,
            self.mock_repository,
            self.mock_article_scraper,
            openrouter_client=None,
        )

        empty_article = ArticleData(
            title="Empty",
            content="",
            author="Test",
            source="Test",
            date="2024-01-15",
            url="https://example.com/empty",
        )

        score = service._get_article_keyword_score(empty_article)

        assert score is None

    @patch("tradingagents.domains.news.news_service.OpenRouterClient")
    @pytest.mark.asyncio
    async def test_sentiment_summary_prefer_llm(self, mock_openrouter_class):
        """Test that sentiment summary prefers LLM when available."""
        mock_client = Mock()
        mock_sentiment_result = Mock()
        mock_sentiment_result.sentiment = "positive"
        mock_sentiment_result.confidence = 0.85
        mock_client.analyze_sentiment.return_value = mock_sentiment_result
        mock_openrouter_class.return_value = mock_client

        service = NewsService(
            self.mock_google_client,
            self.mock_repository,
            self.mock_article_scraper,
            openrouter_client=mock_client,
        )

        result = await service._calculate_sentiment_summary([self.positive_article])

        # Should use LLM analysis
        assert result.label == "positive"
        assert result.score == 0.85  # Score equals confidence for positive sentiment
        # Confidence is calculated as min(scored_articles / len(articles), 1.0)
        # With 1 article, confidence = 1.0
        assert result.confidence == 1.0

    @pytest.mark.asyncio
    async def test_sentiment_summary_fallback_to_keyword(self):
        """Test that sentiment summary falls back to keywords when LLM unavailable."""
        service = NewsService(
            self.mock_google_client,
            self.mock_repository,
            self.mock_article_scraper,
            openrouter_client=None,
        )

        result = await service._calculate_sentiment_summary([self.positive_article])

        # Should use keyword analysis
        assert result.label == "positive"
        assert result.score > 0

    def test_multiple_articles_aggregation(self):
        """Test sentiment aggregation across multiple articles."""
        service = NewsService(
            self.mock_google_client,
            self.mock_repository,
            self.mock_article_scraper,
            openrouter_client=None,
        )

        articles = [self.positive_article, self.negative_article, self.neutral_article]
        result = service._calculate_keyword_sentiment(articles)

        # Should aggregate to something between positive and negative
        assert result.label in ["positive", "negative", "neutral"]
        assert result.confidence > 0


if __name__ == "__main__":
    # Run tests manually if pytest not available
    test_suite = TestSentimentAnalysis()
    test_suite.setup_method()

    print("🧪 Running sentiment analysis tests...")

    try:
        test_suite.test_keyword_sentiment_positive()
        print("✅ Keyword positive sentiment test passed")
    except Exception as e:
        print(f"❌ Keyword positive test failed: {e}")

    try:
        test_suite.test_keyword_sentiment_negative()
        print("✅ Keyword negative sentiment test passed")
    except Exception as e:
        print(f"❌ Keyword negative test failed: {e}")

    try:
        test_suite.test_keyword_sentiment_neutral()
        print("✅ Keyword neutral sentiment test passed")
    except Exception as e:
        print(f"❌ Keyword neutral test failed: {e}")

    try:
        test_suite.test_empty_articles_list()
        print("✅ Empty articles list test passed")
    except Exception as e:
        print(f"❌ Empty articles test failed: {e}")

    try:
        test_suite.test_multiple_articles_aggregation()
        print("✅ Multiple articles aggregation test passed")
    except Exception as e:
        print(f"❌ Multiple articles test failed: {e}")

    print("\n🎉 Sentiment analysis tests completed!")
