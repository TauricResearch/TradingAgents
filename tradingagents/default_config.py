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
    "deep_think_llm": "gpt-5.2",
    "mid_think_llm": None,              # falls back to quick_think_llm when None
    "quick_think_llm": "gpt-5-mini",
    "backend_url": "https://api.openai.com/v1",
    # Per-role provider overrides (fall back to llm_provider / backend_url when None)
    "deep_think_llm_provider": None,    # e.g. "google", "anthropic", "openai"
    "deep_think_backend_url": None,     # override backend URL for deep-think model
    "mid_think_llm_provider": None,     # e.g. "ollama"
    "mid_think_backend_url": None,      # override backend URL for mid-think model
    "quick_think_llm_provider": None,   # e.g. "openai", "ollama"
    "quick_think_backend_url": None,    # override backend URL for quick-think model
    # Provider-specific thinking configuration (applies to all roles unless overridden)
    "google_thinking_level": None,      # "high", "minimal", etc.
    "openai_reasoning_effort": None,    # "medium", "high", "low"
    # Per-role provider-specific thinking configuration
    "deep_think_google_thinking_level": None,
    "deep_think_openai_reasoning_effort": None,
    "mid_think_google_thinking_level": None,
    "mid_think_openai_reasoning_effort": None,
    "quick_think_google_thinking_level": None,
    "quick_think_openai_reasoning_effort": None,
    # Debate and discussion settings
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,
    # Data vendor configuration
    # Category-level configuration (default for all tools in category)
    "data_vendors": {
        "core_stock_apis": "yfinance",       # Options: alpha_vantage, yfinance
        "technical_indicators": "yfinance",  # Options: alpha_vantage, yfinance
        "fundamental_data": "yfinance",      # Options: alpha_vantage, yfinance
        "news_data": "yfinance",             # Options: alpha_vantage, yfinance
        "scanner_data": "yfinance",          # Options: yfinance (primary), alpha_vantage (fallback for movers only)
    },
    # Tool-level configuration (takes precedence over category-level)
    "tool_vendors": {
        # Example: "get_stock_data": "alpha_vantage",  # Override category default
    },
}
