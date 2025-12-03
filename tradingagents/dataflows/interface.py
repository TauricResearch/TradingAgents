from typing import Annotated

# Import from vendor-specific modules
from .local import get_YFin_data, get_finnhub_news, get_finnhub_company_insider_sentiment, get_finnhub_company_insider_transactions, get_simfin_balance_sheet, get_simfin_cashflow, get_simfin_income_statements, get_reddit_global_news, get_reddit_company_news
from .y_finance import get_YFin_data_online, get_stock_stats_indicators_window, get_balance_sheet as get_yfinance_balance_sheet, get_cashflow as get_yfinance_cashflow, get_income_statement as get_yfinance_income_statement, get_insider_transactions as get_yfinance_insider_transactions, validate_ticker as validate_ticker_yfinance
from .google import get_google_news, get_global_news_google
from .openai import get_stock_news_openai, get_global_news_openai, get_fundamentals_openai
from .alpha_vantage import (
    get_stock as get_alpha_vantage_stock,
    get_top_gainers_losers as get_alpha_vantage_movers,
    get_indicator as get_alpha_vantage_indicator,
    get_fundamentals as get_alpha_vantage_fundamentals,
    get_balance_sheet as get_alpha_vantage_balance_sheet,
    get_cashflow as get_alpha_vantage_cashflow,
    get_income_statement as get_alpha_vantage_income_statement,
    get_insider_transactions as get_alpha_vantage_insider_transactions,
    get_news as get_alpha_vantage_news,
    get_global_news as get_alpha_vantage_global_news
)
from .alpha_vantage_common import AlphaVantageRateLimitError
from .reddit_api import get_reddit_news, get_reddit_global_news as get_reddit_api_global_news, get_reddit_trending_tickers, get_reddit_discussions
from .finnhub_api import get_recommendation_trends as get_finnhub_recommendation_trends
from .twitter_data import get_tweets as get_twitter_tweets, get_tweets_from_user as get_twitter_user_tweets

# ============================================================================
# LEGACY COMPATIBILITY LAYER
# ============================================================================
# This module now only provides backward compatibility.
# All new code should use tradingagents.tools.executor.execute_tool() directly.
# ============================================================================

def route_to_vendor(method: str, *args, **kwargs):
    """Route method calls to appropriate vendor implementation with fallback support.

    DEPRECATED: This function now delegates to the new execute_tool() from the registry system.
    Use tradingagents.tools.executor.execute_tool() directly in new code.

    This function is kept for backward compatibility only.
    """
    from tradingagents.tools.executor import execute_tool

    # Delegate to new system
    return execute_tool(method, *args, **kwargs)