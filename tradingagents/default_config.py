import os

DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results"),
    "data_cache_dir": os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
        "dataflows/data_cache",
    ),
    # LLM settings
    "mid_think_llm": "qwen3.5:27b",              # falls back to quick_think_llm when None
    "quick_think_llm": "qwen3.5:27b",
    # Per-role provider overrides (fall back to llm_provider / backend_url when None)
    "deep_think_llm_provider": "openrouter",
    "deep_think_llm": "deepseek/deepseek-r1-0528",
    "deep_think_backend_url": None,     # uses OpenRouter's default URL
    "mid_think_llm_provider": "ollama",     # falls back to ollama
    "mid_think_backend_url": "http://192.168.50.76:11434",      # falls back to backend_url (ollama host)
    "quick_think_llm_provider": "ollama",   # falls back to ollama
    "quick_think_backend_url": "http://192.168.50.76:11434",    # falls back to backend_url (ollama host)
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
    "max_debate_rounds": 2,
    "max_risk_discuss_rounds": 2,
    "max_recur_limit": 100,
    # Data vendor configuration
    # Category-level configuration (default for all tools in category)
    "data_vendors": {
        "core_stock_apis": "yfinance",       # Options: alpha_vantage, yfinance
        "technical_indicators": "yfinance",  # Options: alpha_vantage, yfinance
        "fundamental_data": "yfinance",      # Options: alpha_vantage, yfinance
        "news_data": "yfinance",             # Options: alpha_vantage, yfinance
        "scanner_data": "alpha_vantage",      # Options: alpha_vantage (primary), yfinance (fallback)
    },
    # Tool-level configuration (takes precedence over category-level)
    "tool_vendors": {
        # Example: "get_stock_data": "alpha_vantage",  # Override category default
    },
}
