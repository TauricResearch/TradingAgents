import os

DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results"),
    "data_dir": "/data/coding/trading_agents",
    "data_cache_dir": os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
        "dataflows/data_cache",
    ),
    # LLM settings
    "llm_provider": "openai",
    # "deep_think_llm": "hf.co/unsloth/Qwen3-30B-A3B-Instruct-2507-GGUF:Q5_K_XL",
    # "quick_think_llm": "hf.co/unsloth/Qwen3-30B-A3B-Instruct-2507-GGUF:Q5_K_XL",
    # "deep_think_llm": "hf.co/unsloth/gpt-oss-20b-GGUF:F16",
    # "quick_think_llm": "hf.co/unsloth/gpt-oss-20b-GGUF:F16",
    "deep_think_llm": "gemma3:27b",
    "quick_think_llm": "gemma3:27b",
    # "backend_url": "http://localhost:8080/v1",
    "backend_url": "http://localhost:11434/v1",
    # Debate and discussion settings
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 500,
    # Data vendor configuration
    # Category-level configuration (default for all tools in category)
    "data_vendors": {
        "core_stock_apis": "yfinance",       # Options: yfinance, alpha_vantage, local
        "technical_indicators": "yfinance",  # Options: yfinance, alpha_vantage, local
        "fundamental_data": "alpha_vantage", # Options: openai, alpha_vantage, local
        "news_data": "google",        # Options: openai, alpha_vantage, google, local
    },
    # Tool-level configuration (takes precedence over category-level)
    "tool_vendors": {
        # Example: "get_stock_data": "alpha_vantage",  # Override category default
        # Example: "get_news": "openai",               # Override category default
        "get_stock_data": "yfinance",
        "get_indicators": "yfinance",
        "get_fundamentals": "alpha_vantage",
        "get_balance_sheet": "yfinance",
        "get_cashflow": "yfinance",
        "get_income_statement": "yfinance",
        "get_news": "alpha_vantage",
        "get_global_news": "openai",
        # "get_insider_sentiment": "na",
        "get_insider_transactions": "yfinance",
    },
}