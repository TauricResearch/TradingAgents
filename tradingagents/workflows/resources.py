"""
Dagster resources for TradingAgents workflows.
"""

from dagster import resource

from tradingagents.config import TradingAgentsConfig
from tradingagents.domains.news.news_service import NewsService
from tradingagents.lib.database import DatabaseManager


@resource
def news_service_resource(_init_context):
    """
    Provide a configured NewsService instance for Dagster workflows.

    This resource creates a NewsService with proper database configuration
    for use in Dagster operations.
    """
    config = TradingAgentsConfig.from_env()
    db_manager = DatabaseManager(config.database_url)
    return NewsService.build(db_manager, config)


@resource
def database_manager_resource(_init_context):
    """
    Provide a configured DatabaseManager instance for Dagster workflows.
    """
    config = TradingAgentsConfig.from_env()
    return DatabaseManager(config.database_url)


@resource
def tradingagents_config_resource(_init_context):
    """
    Provide TradingAgents configuration for Dagster workflows.
    """
    return TradingAgentsConfig.from_env()
