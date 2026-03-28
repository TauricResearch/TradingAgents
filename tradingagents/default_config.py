import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env so that TRADINGAGENTS_* variables are available before
# DEFAULT_CONFIG is evaluated.  CWD is checked first, then the project
# root (two levels up from this file).  load_dotenv never overwrites
# variables that are already present in the environment.
load_dotenv()
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _env(key: str, default=None):
    """Read ``TRADINGAGENTS_<KEY>`` from the environment.

    Returns *default* when the variable is unset **or** empty, so that
    ``TRADINGAGENTS_MID_THINK_LLM=`` in a ``.env`` file is treated the
    same as not setting it at all (preserving the ``None`` semantics for
    "fall back to the parent setting").

    This is the single source of truth for config env-var reading.
    Import and reuse this helper instead of duplicating it elsewhere.
    """
    val = os.getenv(f"TRADINGAGENTS_{key.upper()}")
    if not val:  # None or ""
        return default
    return val


def _env_int(key: str, default=None):
    """Like :func:`_env` but coerces the value to ``int``."""
    val = _env(key)
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def _env_float(key: str, default=None):
    """Like :func:`_env` but coerces the value to ``float``."""
    val = _env(key)
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": _env("RESULTS_DIR", "./reports"),
    "data_cache_dir": os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
        "dataflows/data_cache",
    ),
    # LLM settings — all overridable via TRADINGAGENTS_<KEY> env vars
    "llm_provider": _env("LLM_PROVIDER", "openai"),
    "deep_think_llm": _env("DEEP_THINK_LLM", "gpt-5.2"),
    "mid_think_llm": _env("MID_THINK_LLM"),              # falls back to quick_think_llm when None
    "quick_think_llm": _env("QUICK_THINK_LLM", "gpt-5-mini"),
    "backend_url": _env("BACKEND_URL", "https://api.openai.com/v1"),
    # Per-role provider overrides (fall back to llm_provider / backend_url when None)
    "deep_think_llm_provider": _env("DEEP_THINK_LLM_PROVIDER"),    # e.g. "google", "anthropic", "openrouter"
    "deep_think_backend_url": _env("DEEP_THINK_BACKEND_URL"),       # override backend URL for deep-think model
    "mid_think_llm_provider": _env("MID_THINK_LLM_PROVIDER"),      # e.g. "ollama"
    "mid_think_backend_url": _env("MID_THINK_BACKEND_URL"),         # override backend URL for mid-think model
    "quick_think_llm_provider": _env("QUICK_THINK_LLM_PROVIDER"),  # e.g. "openai", "ollama"
    "quick_think_backend_url": _env("QUICK_THINK_BACKEND_URL"),     # override backend URL for quick-think model
    # Per-tier fallback LLM — used automatically when primary model returns 404
    # (e.g. blocked by provider policy). Leave unset to disable auto-retry.
    # Each tier falls back independently; set only the tiers you need.
    #
    # Example .env:
    #   TRADINGAGENTS_QUICK_THINK_FALLBACK_LLM=gpt-5-mini
    #   TRADINGAGENTS_QUICK_THINK_FALLBACK_LLM_PROVIDER=openai
    #   TRADINGAGENTS_MID_THINK_FALLBACK_LLM=gpt-5-mini
    #   TRADINGAGENTS_MID_THINK_FALLBACK_LLM_PROVIDER=openai
    #   TRADINGAGENTS_DEEP_THINK_FALLBACK_LLM=gpt-5.2
    #   TRADINGAGENTS_DEEP_THINK_FALLBACK_LLM_PROVIDER=openai
    "quick_think_fallback_llm":          _env("QUICK_THINK_FALLBACK_LLM"),
    "quick_think_fallback_llm_provider": _env("QUICK_THINK_FALLBACK_LLM_PROVIDER"),
    "mid_think_fallback_llm":            _env("MID_THINK_FALLBACK_LLM"),
    "mid_think_fallback_llm_provider":   _env("MID_THINK_FALLBACK_LLM_PROVIDER"),
    "deep_think_fallback_llm":           _env("DEEP_THINK_FALLBACK_LLM"),
    "deep_think_fallback_llm_provider":  _env("DEEP_THINK_FALLBACK_LLM_PROVIDER"),
    # Provider-specific thinking configuration (applies to all roles unless overridden)
    "google_thinking_level": _env("GOOGLE_THINKING_LEVEL"),      # "high", "minimal", etc.
    "openai_reasoning_effort": _env("OPENAI_REASONING_EFFORT"),  # "medium", "high", "low"
    "anthropic_effort": _env("ANTHROPIC_EFFORT"),                # "high", "medium", "low"
    # Per-role provider-specific thinking configuration
    "deep_think_google_thinking_level": _env("DEEP_THINK_GOOGLE_THINKING_LEVEL"),
    "deep_think_openai_reasoning_effort": _env("DEEP_THINK_OPENAI_REASONING_EFFORT"),
    "mid_think_google_thinking_level": _env("MID_THINK_GOOGLE_THINKING_LEVEL"),
    "mid_think_openai_reasoning_effort": _env("MID_THINK_OPENAI_REASONING_EFFORT"),
    "quick_think_google_thinking_level": _env("QUICK_THINK_GOOGLE_THINKING_LEVEL"),
    "quick_think_openai_reasoning_effort": _env("QUICK_THINK_OPENAI_REASONING_EFFORT"),
    # Debate and discussion settings
    "max_debate_rounds": _env_int("MAX_DEBATE_ROUNDS", 2),
    "max_risk_discuss_rounds": _env_int("MAX_RISK_DISCUSS_ROUNDS", 2),
    "max_recur_limit": _env_int("MAX_RECUR_LIMIT", 100),
    # Concurrency settings
    # Controls how many per-ticker analysis pipelines run in parallel during
    # 'auto' mode (CLI and AgentOS).  Set higher if your API plan supports it.
    "max_concurrent_pipelines": _env_int("MAX_CONCURRENT_PIPELINES", 2),
    # Maximum number of scan-candidate tickers the macro synthesis LLM produces
    # in auto mode.  Portfolio holdings are always included regardless.
    # Set to 0 or leave unset for the default (10).
    "max_auto_tickers": _env_int("MAX_AUTO_TICKERS", 10),
    # Scanner synthesis horizon in calendar days. 30/60/90 map cleanly to
    # the 1–3 month search-graph variants.
    "scan_horizon_days": _env_int("SCAN_HORIZON_DAYS", 30),
    # Data vendor configuration
    # Category-level configuration (default for all tools in category)
    "data_vendors": {
        "core_stock_apis": _env("VENDOR_CORE_STOCK_APIS", "yfinance"),
        "technical_indicators": _env("VENDOR_TECHNICAL_INDICATORS", "yfinance"),
        "fundamental_data": _env("VENDOR_FUNDAMENTAL_DATA", "yfinance"),
        "news_data": _env("VENDOR_NEWS_DATA", "yfinance"),
        "scanner_data": _env("VENDOR_SCANNER_DATA", "yfinance"),
        "calendar_data": _env("VENDOR_CALENDAR_DATA", "finnhub"),
    },
    # Tool-level configuration (takes precedence over category-level)
    "tool_vendors": {
        # Finnhub free tier provides same data + MSPR aggregate bonus signal
        "get_insider_transactions": "finnhub",
        # First implementation is yfinance-only until another vendor is validated.
        "get_gap_candidates": "yfinance",
    },
    # Report storage backend
    # When mongo_uri is set, reports are persisted in MongoDB (never overwritten).
    # Otherwise, the filesystem store is used (run_id prevents same-day overwrites).
    "mongo_uri": _env("MONGO_URI"),                  # e.g. "mongodb://localhost:27017"
    "mongo_db": _env("MONGO_DB", "tradingagents"),   # MongoDB database name
}
