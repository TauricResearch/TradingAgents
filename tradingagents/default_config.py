import os

DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results"),
    "data_dir": "/Users/youssefaitousarrah/Documents/TradingAgents/data",
    "data_cache_dir": os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
        "dataflows/data_cache",
    ),
    # LLM settings
    "llm_provider": "openai",
    "deep_think_llm": "gpt-4o",           # For Google: gemini-2.0-flash or gemini-1.5-pro-latest
    "quick_think_llm": "gpt-4o-mini",     # For Google: gemini-2.0-flash or gemini-1.5-flash-latest
    "backend_url": "https://api.openai.com/v1",
    # Debate and discussion settings
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,
    # Discovery settings
    "discovery": {
        "reddit_trending_limit": 30,      # Number of trending tickers to fetch from Reddit
        "market_movers_limit": 20,        # Number of top gainers/losers to fetch
        "max_candidates_to_analyze": 20,  # Maximum candidates for deep dive analysis
        "news_lookback_days": 7,          # Days of news history to analyze
        "final_recommendations": 10,       # Number of final opportunities to recommend
    },
    # Memory settings
    "enable_memory": False,                   # Enable/disable embeddings and memory system
    "load_historical_memories": False,        # Load pre-built historical memories on startup
    "memory_dir": os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")), "data/memories"),  # Directory for saved memories
    # Data vendor configuration
    # Category-level configuration (default for all tools in category)
    "data_vendors": {
        "core_stock_apis": "yfinance",       # Options: yfinance, alpha_vantage, local
        "technical_indicators": "yfinance",  # Options: yfinance, alpha_vantage, local
        "fundamental_data": "alpha_vantage", # Options: openai, alpha_vantage, local
        "news_data": "reddit,alpha_vantage", # Options: openai, alpha_vantage, google, reddit, local
    },
    # Tool-level configuration (takes precedence over category-level)
    "tool_vendors": {
        # Discovery tools - each tool supports only one vendor
        "get_trending_tickers": "reddit",        # Reddit trending stocks
        "get_market_movers": "alpha_vantage",    # Top gainers/losers
        "get_tweets": "twitter",                 # Twitter API
        "get_tweets_from_user": "twitter",       # Twitter API
        "get_recommendation_trends": "finnhub",  # Analyst recommendations
        # Example: "get_stock_data": "alpha_vantage",  # Override category default
        # Example: "get_news": "openai",               # Override category default
    },
}
