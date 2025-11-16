"""
Main Dagster definitions for TradingAgents workflows.
"""

from dagster import Definitions

from tradingagents.workflows.jobs import (
    complete_news_collection_job,
    simple_news_collection_job,
    single_ticker_news_collection_job,
)
from tradingagents.workflows.news_assets import (
    article_sentiment_analysis,
    article_vector_embeddings,
    daily_sentiment_summary,
    news_articles_table,
    raw_google_news_feeds,
    scraped_article_content,
    trending_topics_analysis,
)
from tradingagents.workflows.resources import (
    database_manager_resource,
    news_service_resource,
    tradingagents_config_resource,
)
from tradingagents.workflows.schedules import (
    daily_news_collection_schedule,
    frequent_news_collection_schedule,
)

# Main Dagster definitions with asset-based approach
defs = Definitions(
    assets=[
        # Core data assets
        raw_google_news_feeds,
        scraped_article_content,
        # Analysis assets
        article_sentiment_analysis,
        article_vector_embeddings,
        # Storage assets
        news_articles_table,
        # Derived analytics assets
        daily_sentiment_summary,
        trending_topics_analysis,
    ],
    jobs=[
        simple_news_collection_job,
        single_ticker_news_collection_job,
        complete_news_collection_job,
    ],
    schedules=[daily_news_collection_schedule, frequent_news_collection_schedule],
    resources={
        "news_service": news_service_resource,
        "database_manager": database_manager_resource,
        "config": tradingagents_config_resource,
    },
)


def define_tradingagents_workspace():
    """
    Define the TradingAgents Dagster workspace.

    Returns:
        Definitions object containing all jobs, schedules, and resources
    """
    return defs
