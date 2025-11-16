"""
Tests for TradingAgents Dagster resources.

Tests resource configuration, dependency injection, and service instantiation.
"""

from unittest.mock import Mock, patch

from tradingagents.lib.database import DatabaseManager
from tradingagents.workflows.resources import (
    database_manager_resource,
    news_service_resource,
    tradingagents_config_resource,
)


class TestResourceConfiguration:
    """Tests for resource configuration and instantiation."""

    @patch("tradingagents.workflows.resources.TradingAgentsConfig.from_env")
    def test_tradingagents_config_resource(self, mock_from_env):
        """Test TradingAgents config resource creation."""
        # Arrange
        mock_config = Mock()
        mock_from_env.return_value = mock_config

        # Act - Call with None since Dagster resources don't need context in tests
        result = tradingagents_config_resource(None)

        # Assert
        assert result == mock_config
        mock_from_env.assert_called_once()

    @patch("tradingagents.workflows.resources.TradingAgentsConfig.from_env")
    def test_database_manager_resource(self, mock_from_env):
        """Test database manager resource creation."""
        # Arrange
        mock_config = Mock()
        mock_config.database_url = "postgresql://test:test@localhost/test"
        mock_from_env.return_value = mock_config

        # Act - Call with None since Dagster resources don't need context in tests
        result = database_manager_resource(None)

        # Assert
        assert isinstance(result, DatabaseManager)
        mock_from_env.assert_called_once()

    @patch("tradingagents.workflows.resources.TradingAgentsConfig.from_env")
    @patch("tradingagents.workflows.resources.DatabaseManager")
    @patch("tradingagents.workflows.resources.NewsService.build")
    def test_news_service_resource(
        self, mock_build_service, mock_database_manager, mock_from_env
    ):
        """Test news service resource creation."""
        # Arrange
        mock_config = Mock()
        mock_config.database_url = "postgresql://test:test@localhost/test"
        mock_from_env.return_value = mock_config

        mock_db_manager = Mock()
        mock_database_manager.return_value = mock_db_manager

        mock_news_service = Mock()
        mock_build_service.return_value = mock_news_service

        # Act - Call with None since Dagster resources don't need context in tests
        result = news_service_resource(None)

        # Assert
        assert result == mock_news_service
        mock_from_env.assert_called_once()
        mock_database_manager.assert_called_once_with(mock_config.database_url)
        mock_build_service.assert_called_once_with(mock_db_manager, mock_config)

    def test_resource_initialization_with_valid_config(self):
        """Test that resources can be initialized with valid configuration."""
        # This test ensures the resource functions don't crash with real config
        # when environment variables are properly set

        # We'll skip actual database connections in unit tests
        # but verify the construction process works
        assert True  # Placeholder for actual resource initialization test


class TestResourceIntegration:
    """Tests for resource integration in workflows."""

    @patch("tradingagents.workflows.resources.TradingAgentsConfig.from_env")
    def test_resource_dependency_injection(self, mock_from_env):
        """Test that resources can be properly injected into operations."""
        # Arrange
        mock_config = Mock()
        mock_config.database_url = "postgresql://test:test@localhost/test"
        mock_from_env.return_value = mock_config

        # Test each resource can be created
        config_resource = tradingagents_config_resource(None)
        db_resource = database_manager_resource(None)
        news_resource = news_service_resource(None)

        # Assert resources are properly configured
        assert config_resource is not None
        assert db_resource is not None
        assert news_resource is not None

    def test_resource_singleton_behavior(self):
        """Test that resources act as singletons (created once per context)."""
        # In Dagster, resources are typically singletons within a run context
        # This test ensures consistent behavior

        # We'd normally test this with Dagster's test utilities
        # For now, we verify the resource functions are stateless
        assert True  # Placeholder for singleton behavior test
