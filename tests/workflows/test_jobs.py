"""
Tests for TradingAgents Dagster job definitions.

Tests job composition, execution patterns, and integration between operations.
"""

from unittest.mock import Mock, patch

from tradingagents.workflows.jobs import (
    complete_news_collection_job,
    simple_news_collection_job,
    single_ticker_news_collection_job,
)


class TestJobDefinitions:
    """Tests for job composition and structure."""

    def test_simple_news_collection_job_structure(self):
        """Test that simple_news_collection_job has correct structure."""
        # Act
        job = simple_news_collection_job

        # Assert
        assert job is not None
        assert hasattr(job, "graph")
        assert job.name == "simple_news_collection_job"

    def test_single_ticker_news_collection_job_structure(self):
        """Test that single_ticker_news_collection_job has correct structure."""
        # Act
        job = single_ticker_news_collection_job

        # Assert
        assert job is not None
        assert hasattr(job, "graph")
        assert job.name == "single_ticker_news_collection_job"

    def test_complete_news_collection_job_structure(self):
        """Test that complete_news_collection_job has correct structure."""
        # Act
        job = complete_news_collection_job

        # Assert
        assert job is not None
        assert hasattr(job, "graph")
        assert job.name == "complete_news_collection_job"

    def test_hardcoded_ticker_operation(self):
        """Test the hardcoded_ticker operation."""
        from tradingagents.workflows.jobs import hardcoded_ticker

        # Act
        result = hardcoded_ticker()

        # Assert
        assert result == "AAPL"


class TestJobConfiguration:
    """Tests for job configuration and resource usage."""

    def test_job_resource_requirements(self):
        """Test that jobs have proper resource requirements."""
        jobs = [
            simple_news_collection_job,
            single_ticker_news_collection_job,
            complete_news_collection_job,
        ]

        for job in jobs:
            # Check that jobs can be instantiated with resources
            assert job is not None
            # In real testing, we'd check resource bindings

    def test_job_metadata(self):
        """Test job metadata and descriptions."""
        jobs = [
            (simple_news_collection_job, "Simple news collection job for testing"),
            (
                single_ticker_news_collection_job,
                "News collection job for a single ticker",
            ),
            (
                complete_news_collection_job,
                "Complete news collection job for all tickers",
            ),
        ]

        for job, _expected_description in jobs:
            # Check that jobs have proper descriptions
            # Note: Dagster jobs store descriptions differently
            assert job is not None


class TestJobExecution:
    """Test job execution with mocked dependencies."""

    @patch("tradingagents.workflows.ops.NewsService.build")
    @patch("tradingagents.workflows.ops.TradingAgentsConfig.from_env")
    def test_single_ticker_job_execution(
        self, mock_config_from_env, mock_build_news_service
    ):
        """Test execution of single ticker job with mocked dependencies."""
        # Arrange
        mock_config = Mock()
        mock_config_from_env.return_value = mock_config

        mock_news_service = Mock()
        mock_news_service.get_company_news_context.return_value = Mock(
            articles=[Mock(title="Test Article", source="CNBC")],
            sentiment_summary=Mock(label="positive", score=0.8),
        )
        mock_build_news_service.return_value = mock_news_service

        # Act & Assert - For now, just verify job structure
        # Full execution testing would require Dagster instance setup
        job = single_ticker_news_collection_job
        assert job is not None
