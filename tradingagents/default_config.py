import os

DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results"),
    "data_cache_dir": os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
        "dataflows/data_cache",
    ),
    # LLM settings
    "llm_provider": "openai",
    "deep_think_llm": "glm-5.1:cloud",
    "quick_think_llm": "glm-5.1:cloud",
    "backend_url": "https://ollama.com/v1",
    # Provider-specific thinking configuration
    "google_thinking_level": None,      # "high", "minimal", etc.
    "openai_reasoning_effort": None,    # "medium", "high", "low"
    # Debate and discussion settings
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,
    # Data vendor configuration
    # Category-level configuration (default for all tools in category).
    # FMP is primary; yfinance/alpha_vantage kept in the fallback chain only.
    "data_vendors": {
        "core_stock_apis": "fmp",       # Options: fmp, yfinance, alpha_vantage
        "technical_indicators": "fmp",  # Options: fmp, yfinance, alpha_vantage
        "fundamental_data": "fmp",      # Options: fmp, yfinance, alpha_vantage
        "news_data": "fmp",             # Options: fmp, yfinance, alpha_vantage
    },
    # Tool-level configuration (takes precedence over category-level)
    "tool_vendors": {
        # Example: "get_stock_data": "alpha_vantage",  # Override category default
    },
}
