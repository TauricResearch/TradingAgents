import os

DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results"),
    "data_dir": "/Users/yluo/Documents/Code/ScAI/FR1-data",
    "data_cache_dir": os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
        "dataflows/data_cache",
    ),
    # LLM settings
    "llm_provider": "openai",
    "deep_think_llm": "o4-mini",
    "quick_think_llm": "gpt-4o-mini",
    "backend_url": "https://api.openai.com/v1",
    "llm_temperature": 0.2,  # Low temperature for deterministic financial analysis
    # Anthropic-specific config for Claude models (using aliases for Claude Max subscription)
    "anthropic_config": {
        "deep_think_llm": "opus",  # Claude Opus 4.5 for deep analysis
        "quick_think_llm": "sonnet",  # Claude Sonnet 4.5 for quick tasks
    },
    # Debate and discussion settings
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,
    # Market configuration
    # Options: "auto" (detect from symbol), "us", "india_nse"
    # When set to "auto", Nifty 50 stocks are automatically detected and routed to NSE vendors
    "market": "auto",
    # Data vendor configuration
    # Category-level configuration (default for all tools in category)
    # For NSE stocks (when market is "auto" or "india_nse"):
    #   - core_stock_apis: jugaad_data (primary), yfinance (fallback)
    #   - technical_indicators: jugaad_data (primary), yfinance (fallback)
    #   - fundamental_data: yfinance (with .NS suffix)
    #   - news_data: google (with company name enhancement)
    "data_vendors": {
        "core_stock_apis": "yfinance",       # Options: yfinance, alpha_vantage, local, jugaad_data
        "technical_indicators": "yfinance",  # Options: yfinance, alpha_vantage, local, jugaad_data
        "fundamental_data": "alpha_vantage", # Options: openai, alpha_vantage, local, yfinance
        "news_data": "alpha_vantage",        # Options: openai, alpha_vantage, google, local
    },
    # Tool-level configuration (takes precedence over category-level)
    "tool_vendors": {
        # Example: "get_stock_data": "alpha_vantage",  # Override category default
        # Example: "get_news": "openai",               # Override category default
    },
}
