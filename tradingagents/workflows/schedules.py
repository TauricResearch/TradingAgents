"""
Dagster schedules for TradingAgents workflows.
"""

from dagster import schedule

from tradingagents.workflows.jobs import complete_news_collection_job


@schedule(
    cron_schedule="0 6 * * *",  # Daily at 6 AM UTC
    job=complete_news_collection_job,
    execution_timezone="UTC",
)
def daily_news_collection_schedule():
    """
    Schedule for daily news collection.

    This schedule runs every day at 6 AM UTC to fetch fresh news
    for all configured tickers. The workflow processes each ticker
    in parallel and each article in parallel, providing comprehensive
    news data for the trading agents.

    Returns:
        Run configuration for the scheduled job
    """
    # Default configuration - can be extended to read from environment
    run_config = {
        "ops": {
            "get_tracked_tickers": {
                "config": {
                    "tickers": ["AAPL", "GOOGL", "MSFT", "TSLA"]  # Default ticker list
                }
            }
        }
    }

    return run_config


@schedule(
    cron_schedule="0 */6 * * *",  # Every 6 hours
    job=complete_news_collection_job,
    execution_timezone="UTC",
)
def frequent_news_collection_schedule():
    """
    Schedule for frequent news collection (every 6 hours).

    This is useful for more time-sensitive trading strategies
    that require more frequent news updates.

    Returns:
        Run configuration for the scheduled job
    """
    run_config = {
        "ops": {
            "get_tracked_tickers": {
                "config": {"tickers": ["AAPL", "GOOGL", "MSFT", "TSLA"]}
            }
        }
    }

    return run_config
