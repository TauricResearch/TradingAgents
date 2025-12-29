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
    # Debate and discussion settings
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,
    # Data vendor configuration
    # Category-level configuration (default for all tools in category)
    "data_vendors": {
        "core_crypto_apis": "binance",       # Options: binance
        "technical_indicators": "taapi",     # Options: taapi
        "fundamental_data": "openai",  # Options: openai
        "news_data": "openai",        # Options: local, openai, telegram
    },
    # Tool-level configuration (takes precedence over category-level)
    "tool_vendors": {
        "get_global_news": "telegram"               # Override category default
    },
    # Tool provider settings
    "tool_providers": {
    },
    "external": {
        "BINANCE_API_KEY": os.getenv("BINANCE_API_KEY", ""),
        "TAAPI_BASE_URL": os.getenv("TAAPI_BASE_URL", "https://api.taapi.io"),
        "TAAPI_API_KEY": os.getenv("TAAPI_API_KEY", ""),
        "BYBIT_BASE_URL": os.getenv("BYBIT_BASE_URL", "https://api-demo.bybit.com"),
        "BYBIT_API_KEY": os.getenv("BYBIT_API_KEY", ""),
        "BYBIT_API_SECRET": os.getenv("BYBIT_API_SECRET", ""),
        "COIN_GECKO_API_BASE_URL": os.getenv("COIN_GECKO_API_BASE_URL", "https://api.coingecko.com/api/v3"),
        "TELEGRAM_API_ID": os.getenv("TELEGRAM_API_ID", ""),
        "TELEGRAM_API_HASH": os.getenv("TELEGRAM_API_HASH", ""),
        "TELEGRAM_SESSION_NAME": os.getenv("TELEGRAM_SESSION_NAME", ""),
    }
}
