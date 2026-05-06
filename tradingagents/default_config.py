import os

_TRADINGAGENTS_HOME = os.path.join(os.path.expanduser("~"), ".tradingagents")

DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", os.path.join(_TRADINGAGENTS_HOME, "logs")),
    "data_cache_dir": os.getenv("TRADINGAGENTS_CACHE_DIR", os.path.join(_TRADINGAGENTS_HOME, "cache")),
    "memory_log_path": os.getenv("TRADINGAGENTS_MEMORY_LOG_PATH", os.path.join(_TRADINGAGENTS_HOME, "memory", "trading_memory.md")),
    # Optional cap on the number of resolved memory log entries.
    "memory_log_max_entries": None,
    # LLM settings
    "llm_provider": "openai",
    "deep_think_llm": "gpt-5.4",
    "quick_think_llm": "gpt-5.4-mini",
    "backend_url": None,
    # Provider-specific thinking configuration
    "google_thinking_level": None,
    "openai_reasoning_effort": None,
    "anthropic_effort": None,
    # Checkpoint/resume.
    "checkpoint_enabled": False,
    # Output language for analyst reports and final decision.
    "output_language": "English",
    # Debate and discussion settings
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,
    # Data vendor configuration. Phase 1 populates these with the
    # crypto/Kalshi vendors actually wired into TOOLS_CATEGORIES.
    "data_vendors": {
        "crypto_price": "coinbase",
        "kalshi_market": "kalshi",
        "crypto_news": "rss",
        "sentiment": "reddit_cmc",
        "on_chain": "free_aggregate",
    },
    # Tool-level overrides (take precedence over category-level).
    "tool_vendors": {},
    # Kalshi execution layer (Phase 3). Defaults are safe — paper-only.
    "kalshi": {
        "paper_mode": True,
        "api_key_id_env": "KALSHI_API_KEY_ID",
        "private_key_path_env": "KALSHI_PRIVATE_KEY_PATH",
        "max_stake_usd": 100.0,
        "max_daily_loss_usd": 200.0,
    },
}
