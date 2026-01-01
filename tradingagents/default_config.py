"""
DEPRECATED: This configuration file is deprecated in favor of the centralized config system.

Please use tradingagents.config instead:
    from tradingagents.config import get_config
    config = get_config()

This file is kept for backwards compatibility only.
"""
import os
import warnings

warnings.warn(
    "tradingagents.default_config is deprecated. Please use 'from tradingagents.config import get_config' instead.",
    DeprecationWarning,
    stacklevel=2
)

DEFAULT_CONFIG = {
    # App config
    "APP_HOST": "localhost",
    "APP_PORT": 8000,
    # Directory settings
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results"),
    "data_dir": "/Users/yluo/Documents/Code/ScAI/FR1-data",
    "data_cache_dir": os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
        "dataflows/data_cache",
    ),
    # LLM settings
    "llm_provider":  os.getenv("LLM_PROVIDER", "openai"),
    "deep_think_llm": os.getenv("DEEP_THINK_LLM", "gpt-4o-mini"),
    "quick_think_llm": os.getenv("QUICK_THINK_LLM", "gpt-4o-mini"),
    "backend_url": os.getenv("BACKEND_URL","https://api.openai.com/v1"),
    # Debate and discussion settings
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,
    # Data vendor configuration
    # Category-level configuration (default for all tools in category)
    "data_vendors": {
        "core_crypto_apis": "bybit",       # Options: binance, bybit
        "core_stock_apis": "yfinance",       # Options: yfinance, alpha_vantage, local
        "technical_indicators": "bybit",     # Options: bybit, taapi
        "fundamental_data": "alpha_vantage",  # Options: openai, alpha_vantage, local
        "news_data": "openai",        # Options: openai, alpha_vantage, google, local
        "profile_data": "bybit",          # Options: bybit, local
    },
    # Tool-level configuration (takes precedence over category-level)
    "tool_vendors": {
        "get_global_news": "telegram"               # Override category default
    },
    # Tool provider settings
    "tool_providers": {
        "TAAPI_BASE_URL": os.getenv("TAAPI_BASE_URL", "https://api.taapi.io"),
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
    },
    "redis": {
        "REDIS_HOST": os.getenv("REDIS_HOST", "localhost"),
        "REDIS_PORT": int(os.getenv("REDIS_PORT", 6379)),
        "REDIS_PASSWORD": os.getenv("REDIS_PASSWORD", "defaultpassword"),
        "REDIS_DB": int(os.getenv("REDIS_DB", 0)),
    },
}
