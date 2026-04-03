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
    "deep_think_llm": "gpt-5.4",
    "quick_think_llm": "gpt-5.4-mini",
    "backend_url": "https://api.openai.com/v1",
    # Provider-specific thinking configuration
    "google_thinking_level": None,      # "high", "minimal", etc.
    "openai_reasoning_effort": None,    # "medium", "high", "low"
    "anthropic_effort": None,           # "high", "medium", "low"
    # Output language for analyst reports and final decision
    # Internal agent debate stays in English for reasoning quality
    "output_language": "English",
    # Debate and discussion settings
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,
    "report_context_char_limit": 16000,
    "debate_history_char_limit": 12000,
    "memory_min_similarity": 0.15,
    # Data vendor configuration
    # Category-level configuration (default for all tools in category)
    "data_vendors": {
        "core_stock_apis": "tushare,yfinance",       # Options: tushare, yfinance
        "technical_indicators": "tushare,yfinance",  # Options: tushare, yfinance
        "fundamental_data": "tushare,yfinance",      # Options: tushare, yfinance
        "news_data": "opencli,brave,yfinance",       # Options: opencli, brave, yfinance
    },
    # Tool-level configuration (takes precedence over category-level)
    "tool_vendors": {
        "get_stock_data": "tushare",
        "get_indicators": "tushare",
        "get_fundamentals": "tushare",
        "get_balance_sheet": "tushare",
        "get_cashflow": "tushare",
        "get_income_statement": "tushare",
        "get_news": "opencli",
        "get_global_news": "opencli",
        "get_insider_transactions": "tushare,yfinance",
    },
}
