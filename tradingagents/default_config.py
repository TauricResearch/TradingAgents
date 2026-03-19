import os

DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results"),
    "data_cache_dir": os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
        "dataflows/data_cache",
    ),

    # LLM routing settings
    # Default: all agents use the same provider/model unless explicitly overridden
    "llm_routing": {
        "default": {
            "provider": "openai",
            "model": "gpt-5-mini",
            "base_url": "https://api.openai.com/v1",
        },
        "roles": {
            # Optional per-role overrides.
            # Leave as None to inherit from "default".
            "market": None,
            "social": None,
            "news": None,
            "fundamentals": None,
            "bull_researcher": None,
            "bear_researcher": None,
            "research_manager": None,
            "trader": None,
            "aggressive_analyst": None,
            "neutral_analyst": None,
            "conservative_analyst": None,
            "portfolio_manager": None,
        },
    },

    # Provider-specific thinking configuration
    # These apply whenever that provider is used.
    "google_thinking_level": None,      # e.g. "high", "minimal"
    "openai_reasoning_effort": None,    # e.g. "medium", "high", "low"

    # Debate and discussion settings
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,

    # Data vendor configuration
    "data_vendors": {
        "core_stock_apis": "yfinance",
        "technical_indicators": "yfinance",
        "fundamental_data": "yfinance",
        "news_data": "yfinance",
    },

    # Tool-level configuration (takes precedence over category-level)
    "tool_vendors": {
        # Example: "get_stock_data": "alpha_vantage",
    },
}