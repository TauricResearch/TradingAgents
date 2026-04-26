import os

DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results"),
    "data_cache_dir": os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
        "dataflows/data_cache",
    ),
    # LLM settings
    "llm_provider": "anthropic",
    "deep_think_llm": "claude-opus-4-6",
    "quick_think_llm": "claude-sonnet-4-6",
    "backend_url": "https://api.anthropic.com/",
    # Anthropic thinking configuration
    "anthropic_effort": None,           # "high", "medium", "low"
    # OpenAI configuration (used when llm_provider = "openai")
    "openai_api_key": None,             # set via CLI or env OPENAI_API_KEY
    # Debate and discussion settings
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,
    # Binance kline configuration (used when routing to Binance)
    "kline_interval": "1d",      # Any KlineInterval value: 1m, 5m, 15m, 1h, 4h, 1d, 1w, 1M
    "kline_start_date": None,    # YYYY-MM-DD; None = 2 months before today at runtime
    "kline_end_date": None,      # YYYY-MM-DD; None = today at runtime
    # Data vendor configuration
    # Category-level configuration (default for all tools in category).
    # Comma-separated = ordered fallback chain (first = primary).
    # cli/main.py overrides these for crypto (sets binance as primary).
    "data_vendors": {
        "core_stock_apis": "yfinance,alpha_vantage",
        "technical_indicators": "yfinance,alpha_vantage",
        "fundamental_data": "yfinance,alpha_vantage",
        "news_data": "yfinance,alpha_vantage",
    },
    # Tool-level configuration (takes precedence over category-level)
    "tool_vendors": {
        # Example: "get_stock_data": "alpha_vantage",  # Override category default
    },
}
