import os

DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("/data/coding/TradingAgents/results", "./results"),
    "data_dir": "/data",
    "data_cache_dir": os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
        "dataflows/data_cache",
    ),
    # LLM settings
    "llm_provider": "ollama",
    # "deep_think_llm": "hf.co/unsloth/Qwen3-30B-A3B-Instruct-2507-GGUF:Q5_K_XL",
    # "quick_think_llm": "hf.co/unsloth/Qwen3-30B-A3B-Instruct-2507-GGUF:Q5_K_XL",
    # "deep_think_llm": "hf.co/unsloth/gpt-oss-20b-GGUF:F16",
    # "quick_think_llm": "hf.co/unsloth/gpt-oss-20b-GGUF:F16",
    # "deep_think_llm": "qwen3:30b",
    # "quick_think_llm": "qwen3:30b",
    # "deep_think_llm": "gpt-oss",
    # "quick_think_llm": "gpt-oss",
    "deep_think_llm": "glm-4.7-flash",
    "quick_think_llm": "glm-4.7-flash",
    # "backend_url": "http://localhost:8080/v1",
    "backend_url": "http://localhost:11434/v1",
    # Debate and discussion settings
    "max_debate_rounds": 5,
    "max_risk_discuss_rounds": 5,
    "max_recur_limit": 100,
    # Data vendor configuration
    # Category-level configuration (default for all tools in category)
    "data_vendors": {
        "core_stock_apis": "yfinance",       # Options: yfinance, alpha_vantage, local
        "technical_indicators": "yfinance",  # Options: yfinance, alpha_vantage, local
        "fundamental_data": "alpha_vantage", # Options: openai, alpha_vantage, local
        "news_data": "local_news",        # Options: openai, alpha_vantage, google, local_news
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
        "get_news": "local_news",
        "get_global_news": "openai",
        # "get_insider_sentiment": "na",
        "get_insider_transactions": "yfinance",
    },
}