import os
from pathlib import Path

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
    "codex_binary": os.getenv("CODEX_BINARY"),
    "codex_reasoning_effort": "medium",
    "codex_summary": "none",
    "codex_personality": "none",
    "codex_workspace_dir": str(Path.home() / ".codex" / "tradingagents-workspace"),
    "codex_request_timeout": 120.0,
    "codex_max_retries": 2,
    "codex_cleanup_threads": True,
    # Output language for analyst reports and final decision
    # Internal agent debate stays in English for reasoning quality
    "output_language": "English",
    # Debate and discussion settings
    "max_debate_rounds": 2,
    "max_risk_discuss_rounds": 2,
    "max_recur_limit": 100,
    "market_country": "US",
    "timezone": "US/Eastern",
    "enable_no_trade": True,
    "vendor_timeout": 15,
    "empty_result_fallback": True,
    "memory_n_matches": 3,
    # Data vendor configuration
    # Category-level configuration (default for all tools in category)
    "data_vendors": {
        "core_stock_apis": "yfinance",       # Options: alpha_vantage, yfinance
        "technical_indicators": "yfinance",  # Options: alpha_vantage, yfinance
        "fundamental_data": "yfinance",      # Options: alpha_vantage, yfinance
        "news_data": "alpha_vantage,yfinance",  # Options: alpha_vantage, yfinance, naver
        "macro_data": "alpha_vantage,yfinance",  # Options: alpha_vantage, yfinance, ecos
        "disclosure_data": "opendart",  # Options: opendart
        "social_data": "yfinance",  # Options: yfinance, naver
    },
    # Tool-level configuration (takes precedence over category-level)
    "tool_vendors": {
        # Example: "get_company_news": "naver,yfinance",  # Override category default
        # Example: "get_macro_news": "ecos,alpha_vantage,yfinance",
        # Example: "get_stock_data": "alpha_vantage",
    },
    "api_keys_path": str(Path(__file__).resolve().parents[1] / "Docs" / "list_api_keys.md"),
}
