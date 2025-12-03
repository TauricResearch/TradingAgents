import os

DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results"),
    "data_dir": os.getenv("TRADINGAGENTS_DATA_DIR", "./data"),
    "data_cache_dir": os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
        "dataflows/data_cache",
    ),
    "llm_provider": "openai",
    "deep_think_llm": "gpt-5",
    "quick_think_llm": "gpt-5-mini",
    "backend_url": "https://api.openai.com/v1",
    "max_debate_rounds": 2,
    "max_risk_discuss_rounds": 2,
    "max_recur_limit": 100,
    "data_vendors": {
        "core_stock_apis": "yfinance",
        "technical_indicators": "yfinance",
        "fundamental_data": "alpha_vantage",
        "news_data": "alpha_vantage",
    },
    "tool_vendors": {},
    "discovery_timeout": 60,
    "discovery_hard_timeout": 120,
    "discovery_cache_ttl": 300,
    "discovery_max_results": 20,
    "discovery_min_mentions": 2,
    "bulk_news_vendor_order": ["tavily", "brave", "alpha_vantage", "openai", "google"],
    "bulk_news_timeout": 30,
    "bulk_news_max_retries": 3,
    "log_level": os.getenv("TRADINGAGENTS_LOG_LEVEL", "INFO"),
    "log_dir": os.getenv("TRADINGAGENTS_LOG_DIR", "./logs"),
    "log_console_enabled": os.getenv("TRADINGAGENTS_LOG_CONSOLE", "true").lower()
    in ("true", "1", "yes", "on"),
    "log_file_enabled": os.getenv("TRADINGAGENTS_LOG_FILE", "true").lower()
    in ("true", "1", "yes", "on"),
}
