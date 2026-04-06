"""
Tool Registry - Single Source of Truth for All Trading Tools

This registry defines ALL tools with their complete metadata:
- Which agents use them
- Which vendors provide them (with actual function references)
- Vendor priority for fallback
- Function signatures

Adding a new tool: Just add one entry here, everything else is auto-generated.
"""

from typing import Any, Dict, List, Optional

from tradingagents.dataflows.alpha_vantage import (
    get_balance_sheet as get_alpha_vantage_balance_sheet,
)
from tradingagents.dataflows.alpha_vantage import (
    get_cashflow as get_alpha_vantage_cashflow,
)
from tradingagents.dataflows.alpha_vantage import (
    get_fundamentals as get_alpha_vantage_fundamentals,
)
from tradingagents.dataflows.alpha_vantage import (
    get_income_statement as get_alpha_vantage_income_statement,
)
from tradingagents.dataflows.alpha_vantage import (
    get_insider_sentiment as get_alpha_vantage_insider_sentiment,
)
from tradingagents.dataflows.alpha_vantage import (
    get_stock as get_alpha_vantage_stock,
)
from tradingagents.dataflows.alpha_vantage import (
    get_top_gainers_losers as get_alpha_vantage_movers,
)
from tradingagents.dataflows.alpha_vantage_analysts import (
    get_alpha_vantage_analyst_changes,
)
from tradingagents.dataflows.alpha_vantage_volume import (
    get_alpha_vantage_unusual_volume,
    get_cached_average_volume,
    get_cached_average_volume_batch,
)
from tradingagents.dataflows.finnhub_api import (
    get_earnings_calendar as get_finnhub_earnings_calendar,
)
from tradingagents.dataflows.finnhub_api import (
    get_ipo_calendar as get_finnhub_ipo_calendar,
)
from tradingagents.dataflows.finnhub_api import (
    get_recommendation_trends as get_finnhub_recommendation_trends,
)
from tradingagents.dataflows.finviz_scraper import (
    get_finviz_insider_buying,
    get_finviz_short_interest,
)
from tradingagents.dataflows.openai import (
    get_fundamentals_openai,
    get_global_news_openai,
    get_stock_news_openai,
)
from tradingagents.dataflows.reddit_api import (
    get_reddit_discussions,
    get_reddit_news,
    get_reddit_trending_tickers,
    get_reddit_undiscovered_dd,
)
from tradingagents.dataflows.reddit_api import (
    get_reddit_global_news as get_reddit_api_global_news,
)
from tradingagents.dataflows.tradier_api import (
    get_tradier_unusual_options,
)
from tradingagents.dataflows.twitter_data import (
    get_tweets as get_twitter_tweets,
)
from tradingagents.dataflows.y_finance import (
    get_balance_sheet as get_yfinance_balance_sheet,
)
from tradingagents.dataflows.y_finance import (
    get_cashflow as get_yfinance_cashflow,
)
from tradingagents.dataflows.y_finance import (
    get_fundamentals as get_yfinance_fundamentals,
)
from tradingagents.dataflows.y_finance import (
    get_income_statement as get_yfinance_income_statement,
)
from tradingagents.dataflows.y_finance import (
    get_insider_transactions as get_yfinance_insider_transactions,
)
from tradingagents.dataflows.y_finance import (
    get_options_activity as get_yfinance_options_activity,
)

# Import all vendor implementations
from tradingagents.dataflows.y_finance import (
    get_technical_analysis,
    get_YFin_data_online,
)
from tradingagents.dataflows.y_finance import (
    validate_ticker as validate_ticker_yfinance,
)
from tradingagents.dataflows.y_finance import (
    validate_tickers_batch as validate_tickers_batch_yfinance,
)
from tradingagents.utils.logger import get_logger

logger = get_logger(__name__)

# ============================================================================
# TOOL REGISTRY - SINGLE SOURCE OF TRUTH
# ============================================================================

TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {
    # ========== CORE STOCK APIs ==========
    "get_stock_data": {
        "description": "Retrieve stock price data (OHLCV) for a given ticker symbol",
        "category": "core_stock_apis",
        "agents": ["market"],
        "vendors": {
            "yfinance": get_YFin_data_online,
            "alpha_vantage": get_alpha_vantage_stock,
        },
        "vendor_priority": ["yfinance"],
        "parameters": {
            "symbol": {"type": "str", "description": "Ticker symbol of the company (e.g., AAPL)"},
            "start_date": {"type": "str", "description": "Start date in yyyy-mm-dd format"},
            "end_date": {"type": "str", "description": "End date in yyyy-mm-dd format"},
        },
        "returns": "str: Formatted dataframe containing stock price data",
    },
    "validate_ticker": {
        "description": "Validate if a ticker symbol exists and is tradeable",
        "category": "core_stock_apis",
        "agents": [],
        "vendors": {
            "yfinance": validate_ticker_yfinance,
        },
        "vendor_priority": ["yfinance"],
        "parameters": {
            "symbol": {"type": "str", "description": "Ticker symbol to validate"},
        },
        "returns": "bool: True if valid, False otherwise",
    },
    "validate_tickers_batch": {
        "description": "Validate multiple ticker symbols using Yahoo Finance quote endpoint",
        "category": "core_stock_apis",
        "agents": [],
        "vendors": {
            "yfinance": validate_tickers_batch_yfinance,
        },
        "vendor_priority": ["yfinance"],
        "parameters": {
            "symbols": {"type": "list[str]", "description": "Ticker symbols to validate"},
        },
        "returns": "dict: valid/invalid ticker lists",
    },
    "get_average_volume": {
        "description": "Get average trading volume over a recent window (cached, with fallback download)",
        "category": "core_stock_apis",
        "agents": [],
        "vendors": {
            "volume_cache": get_cached_average_volume,
        },
        "vendor_priority": ["volume_cache"],
        "parameters": {
            "symbol": {"type": "str", "description": "Ticker symbol"},
            "lookback_days": {"type": "int", "description": "Days to average", "default": 20},
            "curr_date": {
                "type": "str",
                "description": "Current date, YYYY-mm-dd",
                "default": None,
            },
            "cache_key": {"type": "str", "description": "Cache key/universe", "default": "default"},
            "fallback_download": {
                "type": "bool",
                "description": "Download if cache missing",
                "default": True,
            },
        },
        "returns": "dict: average and latest volume metadata",
    },
    "get_average_volume_batch": {
        "description": "Get average trading volumes for multiple tickers using cached data",
        "category": "core_stock_apis",
        "agents": [],
        "vendors": {
            "volume_cache": get_cached_average_volume_batch,
        },
        "vendor_priority": ["volume_cache"],
        "parameters": {
            "symbols": {"type": "list[str]", "description": "Ticker symbols"},
            "lookback_days": {"type": "int", "description": "Days to average", "default": 20},
            "curr_date": {
                "type": "str",
                "description": "Current date, YYYY-mm-dd",
                "default": None,
            },
            "cache_key": {"type": "str", "description": "Cache key/universe", "default": "default"},
            "fallback_download": {
                "type": "bool",
                "description": "Download if cache missing",
                "default": True,
            },
        },
        "returns": "dict: mapping of ticker to volume metadata",
    },
    # ========== TECHNICAL INDICATORS ==========
    # "get_indicators": {
    #     "description": "Get concise technical analysis with signals, trends, and key indicator interpretations",
    #     "category": "technical_indicators",
    #     "agents": ["market"],
    #     "vendors": {
    #         "yfinance": get_technical_analysis,
    #     },
    #     "vendor_priority": ["yfinance"],
    #     "parameters": {
    #         "symbol": {"type": "str", "description": "Ticker symbol"},
    #         "curr_date": {"type": "str", "description": "Current trading date, YYYY-mm-dd"},
    #     },
    #     "returns": "str: Concise analysis with RSI signals, MACD crossovers, MA trends, Bollinger position, and ATR volatility",
    # },
    "get_indicators": {
        "description": "Get concise technical analysis with signals, trends, and key indicator interpretations",
        "category": "technical_indicators",
        "agents": ["market"],
        "vendors": {
            "yfinance": get_technical_analysis,
        },
        "vendor_priority": ["yfinance"],
        "parameters": {
            "symbol": {"type": "str", "description": "Ticker symbol"},
            "curr_date": {"type": "str", "description": "Current trading date, YYYY-mm-dd"},
        },
        "returns": "str: Concise analysis with RSI signals, MACD crossovers, MA trends, Bollinger position, and ATR volatility",
    },
    # ========== FUNDAMENTAL DATA ==========
    "get_fundamentals": {
        "description": "Retrieve comprehensive fundamental data for a ticker",
        "category": "fundamental_data",
        "agents": ["fundamentals"],
        "vendors": {
            "yfinance": get_yfinance_fundamentals,
            "alpha_vantage": get_alpha_vantage_fundamentals,
            "openai": get_fundamentals_openai,
        },
        "vendor_priority": ["yfinance", "openai"],
        "parameters": {
            "ticker": {"type": "str", "description": "Ticker symbol"},
            "curr_date": {"type": "str", "description": "Current date, yyyy-mm-dd"},
        },
        "returns": "str: Comprehensive fundamental data report",
    },
    "get_balance_sheet": {
        "description": "Retrieve balance sheet data for a ticker",
        "category": "fundamental_data",
        "agents": ["fundamentals"],
        "vendors": {
            "alpha_vantage": get_alpha_vantage_balance_sheet,
            "yfinance": get_yfinance_balance_sheet,
        },
        "vendor_priority": ["alpha_vantage", "yfinance"],
        "parameters": {
            "ticker": {"type": "str", "description": "Ticker symbol"},
        },
        "returns": "str: Balance sheet data",
    },
    "get_cashflow": {
        "description": "Retrieve cash flow statement for a ticker",
        "category": "fundamental_data",
        "agents": ["fundamentals"],
        "vendors": {
            "alpha_vantage": get_alpha_vantage_cashflow,
            "yfinance": get_yfinance_cashflow,
        },
        "vendor_priority": ["alpha_vantage", "yfinance"],
        "parameters": {
            "ticker": {"type": "str", "description": "Ticker symbol"},
        },
        "returns": "str: Cash flow statement data",
    },
    "get_income_statement": {
        "description": "Retrieve income statement for a ticker",
        "category": "fundamental_data",
        "agents": ["fundamentals"],
        "vendors": {
            "alpha_vantage": get_alpha_vantage_income_statement,
            "yfinance": get_yfinance_income_statement,
        },
        "vendor_priority": ["alpha_vantage", "yfinance"],
        "parameters": {
            "ticker": {"type": "str", "description": "Ticker symbol"},
        },
        "returns": "str: Income statement data",
    },
    "get_recommendation_trends": {
        "description": "Retrieve analyst recommendation trends",
        "category": "fundamental_data",
        "agents": ["fundamentals"],
        "vendors": {
            "finnhub": get_finnhub_recommendation_trends,
        },
        "vendor_priority": ["finnhub"],
        "parameters": {
            "ticker": {"type": "str", "description": "Ticker symbol"},
        },
        "returns": "str: Analyst recommendation trends",
    },
    # ========== NEWS & INSIDER DATA ==========
    "get_news": {
        "description": "Retrieve news articles for a specific ticker",
        "category": "news_data",
        "agents": ["news", "social"],
        "vendors": {
            # "alpha_vantage": get_alpha_vantage_news,
            "reddit": get_reddit_news,
            "openai": get_stock_news_openai,
            # "google": get_google_news,
        },
        "vendor_priority": ["reddit", "openai"],
        "execution_mode": "aggregate",
        "aggregate_vendors": ["reddit", "openai"],
        "parameters": {
            "query": {"type": "str", "description": "Search query or ticker symbol"},
            "start_date": {"type": "str", "description": "Start date, yyyy-mm-dd"},
            "end_date": {"type": "str", "description": "End date, yyyy-mm-dd"},
        },
        "returns": "str: News articles and analysis",
    },
    "get_global_news": {
        "description": "Retrieve global market news and macroeconomic updates",
        "category": "news_data",
        "agents": ["news"],
        "vendors": {
            "openai": get_global_news_openai,
            # "google": get_global_news_google,
            "reddit": get_reddit_api_global_news,
            # "alpha_vantage": get_alpha_vantage_global_news,
        },
        "vendor_priority": ["openai", "reddit"],
        "execution_mode": "aggregate",
        "parameters": {
            "date": {"type": "str", "description": "Date for news, yyyy-mm-dd"},
            "look_back_days": {"type": "int", "description": "Days to look back", "default": 7},
            "limit": {
                "type": "int",
                "description": "Number of articles/topics to return",
                "default": 5,
            },
        },
        "returns": "str: Global news and macro updates",
    },
    "get_insider_sentiment": {
        "description": "Retrieve insider trading sentiment analysis",
        "category": "news_data",
        "agents": ["news"],
        "vendors": {
            "alpha_vantage": get_alpha_vantage_insider_sentiment,
        },
        "vendor_priority": ["alpha_vantage"],
        "parameters": {
            "ticker": {"type": "str", "description": "Ticker symbol"},
        },
        "returns": "str: Insider sentiment analysis",
    },
    "get_insider_transactions": {
        "description": "Retrieve insider transaction history",
        "category": "news_data",
        "agents": ["news"],
        "vendors": {
            "yfinance": get_yfinance_insider_transactions,
        },
        "vendor_priority": ["yfinance"],
        "parameters": {
            "ticker": {"type": "str", "description": "Ticker symbol"},
        },
        "returns": "str: Insider transaction history",
    },
    # ========== DISCOVERY TOOLS ==========
    # (Used by discovery mode, not bound to regular analysis agents)
    "get_trending_tickers": {
        "description": "Get trending stock tickers from social media",
        "category": "discovery",
        "agents": [],
        "vendors": {
            "reddit": get_reddit_trending_tickers,
        },
        "vendor_priority": ["reddit"],
        "parameters": {
            "limit": {"type": "int", "description": "Number of tickers to return", "default": 15},
        },
        "returns": "str: List of trending tickers with sentiment",
    },
    "get_market_movers": {
        "description": "Get top market gainers and losers",
        "category": "discovery",
        "agents": [],
        "vendors": {
            "alpha_vantage": get_alpha_vantage_movers,
        },
        "vendor_priority": ["alpha_vantage"],
        "parameters": {
            "limit": {"type": "int", "description": "Number of movers to return", "default": 10},
        },
        "returns": "str: Top gainers and losers",
    },
    "get_tweets": {
        "description": "Get tweets related to stocks or market topics",
        "category": "discovery",
        "agents": [],
        "vendors": {
            "twitter": get_twitter_tweets,
        },
        "vendor_priority": ["twitter"],
        "parameters": {
            "query": {"type": "str", "description": "Search query"},
            "count": {"type": "int", "description": "Number of tweets", "default": 20},
        },
        "returns": "str: Tweets matching the query",
    },
    "get_earnings_calendar": {
        "description": "Get upcoming earnings announcements (catalysts for volatility)",
        "category": "discovery",
        "agents": [],
        "vendors": {
            "finnhub": get_finnhub_earnings_calendar,
        },
        "vendor_priority": ["finnhub"],
        "parameters": {
            "from_date": {"type": "str", "description": "Start date in yyyy-mm-dd format"},
            "to_date": {"type": "str", "description": "End date in yyyy-mm-dd format"},
        },
        "returns": "str: Formatted earnings calendar with EPS and revenue estimates",
    },
    "get_ipo_calendar": {
        "description": "Get upcoming and recent IPOs (new listing opportunities)",
        "category": "discovery",
        "agents": [],
        "vendors": {
            "finnhub": get_finnhub_ipo_calendar,
        },
        "vendor_priority": ["finnhub"],
        "parameters": {
            "from_date": {"type": "str", "description": "Start date in yyyy-mm-dd format"},
            "to_date": {"type": "str", "description": "End date in yyyy-mm-dd format"},
        },
        "returns": "str: Formatted IPO calendar with pricing and share details",
    },
    "get_unusual_volume": {
        "description": "Find stocks with unusual volume but minimal price movement (accumulation signal)",
        "category": "discovery",
        "agents": [],
        "vendors": {
            "alpha_vantage": get_alpha_vantage_unusual_volume,
        },
        "vendor_priority": ["alpha_vantage"],
        "parameters": {
            "date": {
                "type": "str",
                "description": "Analysis date in yyyy-mm-dd format",
                "default": None,
            },
            "min_volume_multiple": {
                "type": "float",
                "description": "Minimum volume multiple vs average",
                "default": 3.0,
            },
            "max_price_change": {
                "type": "float",
                "description": "Maximum price change percentage",
                "default": 5.0,
            },
            "top_n": {
                "type": "int",
                "description": "Number of top results to return",
                "default": 20,
            },
        },
        "returns": "str: Formatted report of stocks with unusual volume patterns",
    },
    "get_unusual_options_activity": {
        "description": "Analyze options activity for specific tickers as confirmation signal (not for primary discovery)",
        "category": "discovery",
        "agents": [],
        "vendors": {
            "yfinance": get_yfinance_options_activity,
            "tradier": get_tradier_unusual_options,
        },
        "vendor_priority": ["yfinance"],
        "parameters": {
            "ticker": {"type": "str", "description": "Ticker symbol to analyze"},
            "num_expirations": {
                "type": "int",
                "description": "Number of nearest expiration dates to analyze",
                "default": 3,
            },
            "curr_date": {
                "type": "str",
                "description": "Analysis date for reference",
                "default": None,
            },
        },
        "returns": "str: Formatted report of options activity with put/call ratios",
    },
    "get_analyst_rating_changes": {
        "description": "Track recent analyst upgrades/downgrades and price target changes",
        "category": "discovery",
        "agents": [],
        "vendors": {
            "alpha_vantage": get_alpha_vantage_analyst_changes,
        },
        "vendor_priority": ["alpha_vantage"],
        "parameters": {
            "lookback_days": {
                "type": "int",
                "description": "Number of days to look back",
                "default": 7,
            },
            "change_types": {
                "type": "list",
                "description": "Types of changes to track",
                "default": ["upgrade", "downgrade", "initiated"],
            },
            "top_n": {"type": "int", "description": "Number of top results", "default": 20},
        },
        "returns": "str: Formatted report of recent analyst rating changes with freshness indicators",
    },
    "get_short_interest": {
        "description": "Discover stocks with high short interest by scraping Finviz screener (squeeze candidates)",
        "category": "discovery",
        "agents": [],
        "vendors": {
            "finviz": get_finviz_short_interest,
        },
        "vendor_priority": ["finviz"],
        "parameters": {
            "min_short_interest_pct": {
                "type": "float",
                "description": "Minimum short interest % of float",
                "default": 10.0,
            },
            "min_days_to_cover": {
                "type": "float",
                "description": "Minimum days to cover ratio",
                "default": 2.0,
            },
            "top_n": {"type": "int", "description": "Number of top results", "default": 20},
        },
        "returns": "str: Formatted report of discovered high short interest stocks with squeeze potential",
    },
    "get_insider_buying": {
        "description": "Discover stocks with significant insider buying activity (leading indicator)",
        "category": "discovery",
        "agents": [],
        "vendors": {
            "finviz": get_finviz_insider_buying,
        },
        "vendor_priority": ["finviz"],
        "parameters": {
            "transaction_type": {
                "type": "str",
                "description": "Transaction type: 'buy', 'sell', or 'any'",
                "default": "buy",
            },
            "top_n": {"type": "int", "description": "Number of top results", "default": 20},
            "lookback_days": {"type": "int", "description": "Days to look back", "default": 3},
            "min_value": {
                "type": "int",
                "description": "Minimum transaction value",
                "default": 25000,
            },
        },
        "returns": "str: Formatted report of stocks with recent insider buying/selling activity",
    },
    "get_reddit_discussions": {
        "description": "Get Reddit discussions about a specific ticker",
        "category": "news_data",
        "agents": ["social"],
        "vendors": {
            "reddit": get_reddit_discussions,
        },
        "vendor_priority": ["reddit"],
        "parameters": {
            "symbol": {"type": "str", "description": "Ticker symbol"},
            "from_date": {"type": "str", "description": "Start date, yyyy-mm-dd"},
            "to_date": {"type": "str", "description": "End date, yyyy-mm-dd"},
        },
        "returns": "str: Reddit discussions and sentiment",
    },
    "scan_reddit_dd": {
        "description": "Scan Reddit for high-quality due diligence posts",
        "category": "discovery",
        "agents": ["social"],
        "vendors": {
            "reddit": get_reddit_undiscovered_dd,
        },
        "vendor_priority": ["reddit"],
        "parameters": {
            "lookback_hours": {"type": "int", "description": "Hours to look back", "default": 72},
            "scan_limit": {
                "type": "int",
                "description": "Number of new posts to scan",
                "default": 100,
            },
            "top_n": {
                "type": "int",
                "description": "Number of top DD posts to return",
                "default": 10,
            },
            "num_comments": {
                "type": "int",
                "description": "Number of top comments to include",
                "default": 10,
            },
        },
        "returns": "str: Report of high-quality undiscovered DD",
    },
    "get_options_activity": {
        "description": "Get options activity for a specific ticker (volume, open interest, put/call ratios, unusual activity)",
        "category": "discovery",
        "agents": ["fundamentals"],
        "vendors": {
            "yfinance": get_yfinance_options_activity,
            "tradier": get_tradier_unusual_options,
        },
        "vendor_priority": ["yfinance"],
        "parameters": {
            "ticker": {"type": "str", "description": "Ticker symbol"},
            "num_expirations": {
                "type": "int",
                "description": "Number of nearest expiration dates to analyze",
                "default": 3,
            },
            "curr_date": {
                "type": "str",
                "description": "Current date for reference",
                "default": None,
            },
        },
        "returns": "str: Options activity report with volume, OI, P/C ratios, and unusual activity",
    },
}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def get_tools_for_agent(agent_name: str) -> List[str]:
    """Get list of tool names available to a specific agent.

    Args:
        agent_name: Name of the agent (e.g., "market", "news", "fundamentals")

    Returns:
        List of tool names that the agent can use
    """
    return [
        tool_name
        for tool_name, metadata in TOOL_REGISTRY.items()
        if agent_name in metadata["agents"]
    ]


def get_tool_metadata(tool_name: str) -> Optional[Dict[str, Any]]:
    """Get complete metadata for a specific tool.

    Args:
        tool_name: Name of the tool

    Returns:
        Tool metadata dictionary, or None if tool doesn't exist
    """
    return TOOL_REGISTRY.get(tool_name)


def get_all_tools() -> List[str]:
    """Get list of all available tool names.

    Returns:
        List of all tool names in the registry
    """
    return list(TOOL_REGISTRY.keys())


def get_tools_by_category(category: str) -> List[str]:
    """Get all tools in a specific category.

    Args:
        category: Category name (e.g., "fundamental_data", "news_data")

    Returns:
        List of tool names in that category
    """
    return [
        tool_name
        for tool_name, metadata in TOOL_REGISTRY.items()
        if metadata["category"] == category
    ]


def get_vendor_config(tool_name: str) -> Dict[str, Any]:
    """Get vendor configuration for a tool.

    Args:
        tool_name: Name of the tool

    Returns:
        Dict with "vendors" (dict of vendor functions) and "vendor_priority" (list)
    """
    metadata = get_tool_metadata(tool_name)
    if not metadata:
        return {"vendors": {}, "vendor_priority": []}

    return {
        "vendors": metadata.get("vendors", {}),
        "vendor_priority": metadata.get("vendor_priority", []),
    }


# ============================================================================
# AGENT-TOOL MAPPING
# ============================================================================


def get_agent_tool_mapping() -> Dict[str, List[str]]:
    """Get complete mapping of agents to their tools.

    Returns:
        Dictionary mapping agent names to lists of tool names
    """
    mapping = {}

    # Collect all agents mentioned in registry
    all_agents = set()
    for metadata in TOOL_REGISTRY.values():
        all_agents.update(metadata["agents"])

    # Build mapping for each agent
    for agent in all_agents:
        mapping[agent] = get_tools_for_agent(agent)

    return mapping


# ============================================================================
# VALIDATION
# ============================================================================


def validate_registry() -> List[str]:
    """Validate the tool registry for common issues.

    Returns:
        List of warning/error messages (empty if all valid)
    """
    issues = []

    for tool_name, metadata in TOOL_REGISTRY.items():
        # Check required fields
        required_fields = [
            "description",
            "category",
            "agents",
            "vendors",
            "vendor_priority",
            "parameters",
            "returns",
        ]
        for field in required_fields:
            if field not in metadata:
                issues.append(f"{tool_name}: Missing required field '{field}'")

        # Check vendor configuration
        if not metadata.get("vendor_priority"):
            issues.append(f"{tool_name}: No vendors specified in vendor_priority")

        if not metadata.get("vendors"):
            issues.append(f"{tool_name}: No vendor functions specified")

        # Verify vendor_priority matches vendors dict
        vendor_priority = metadata.get("vendor_priority", [])
        vendors = metadata.get("vendors", {})
        for vendor_name in vendor_priority:
            if vendor_name not in vendors:
                issues.append(
                    f"{tool_name}: Vendor '{vendor_name}' in priority list but not in vendors dict"
                )

        # Check parameters
        if not isinstance(metadata.get("parameters"), dict):
            issues.append(f"{tool_name}: Parameters must be a dictionary")

        # Validate execution_mode if present
        if "execution_mode" in metadata:
            execution_mode = metadata["execution_mode"]
            if execution_mode not in ["fallback", "aggregate"]:
                issues.append(
                    f"{tool_name}: Invalid execution_mode '{execution_mode}', must be 'fallback' or 'aggregate'"
                )

        # Validate aggregate_vendors if present
        if "aggregate_vendors" in metadata:
            aggregate_vendors = metadata["aggregate_vendors"]
            if not isinstance(aggregate_vendors, list):
                issues.append(f"{tool_name}: aggregate_vendors must be a list")
            else:
                for vendor_name in aggregate_vendors:
                    if vendor_name not in vendors:
                        issues.append(
                            f"{tool_name}: aggregate_vendor '{vendor_name}' not in vendors dict"
                        )

            # Warn if aggregate_vendors specified but execution_mode is not aggregate
            if metadata.get("execution_mode") != "aggregate":
                issues.append(
                    f"{tool_name}: aggregate_vendors specified but execution_mode is not 'aggregate'"
                )

    return issues


if __name__ == "__main__":
    # Example usage and validation
    logger.info("=" * 70)
    logger.info("TOOL REGISTRY OVERVIEW")
    logger.info("=" * 70)

    logger.info(f"Total tools: {len(TOOL_REGISTRY)}")

    logger.info("Tools by category:")
    categories = set(m["category"] for m in TOOL_REGISTRY.values())
    for category in sorted(categories):
        tools = get_tools_by_category(category)
        logger.info(f"  {category}: {len(tools)} tools")
        for tool in tools:
            logger.debug(f"    - {tool}")

    logger.info("Agent-Tool Mapping:")
    mapping = get_agent_tool_mapping()
    for agent, tools in sorted(mapping.items()):
        logger.info(f"  {agent}: {len(tools)} tools")
        for tool in tools:
            logger.debug(f"    - {tool}")

    logger.info("Validation:")
    issues = validate_registry()
    if issues:
        logger.warning("⚠️  Issues found:")
        for issue in issues:
            logger.warning(f"  - {issue}")
    else:
        logger.info("✅ Registry is valid!")
