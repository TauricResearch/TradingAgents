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


DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": _env("RESULTS_DIR", "./results"),
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
    # Provider-specific thinking configuration (applies to all roles unless overridden)
    "google_thinking_level": _env("GOOGLE_THINKING_LEVEL"),      # "high", "minimal", etc.
    "openai_reasoning_effort": _env("OPENAI_REASONING_EFFORT"),  # "medium", "high", "low"
    # Per-role provider-specific thinking configuration
    "deep_think_google_thinking_level": _env("DEEP_THINK_GOOGLE_THINKING_LEVEL"),
    "deep_think_openai_reasoning_effort": _env("DEEP_THINK_OPENAI_REASONING_EFFORT"),
    "mid_think_google_thinking_level": _env("MID_THINK_GOOGLE_THINKING_LEVEL"),
    "mid_think_openai_reasoning_effort": _env("MID_THINK_OPENAI_REASONING_EFFORT"),
    "quick_think_google_thinking_level": _env("QUICK_THINK_GOOGLE_THINKING_LEVEL"),
    "quick_think_openai_reasoning_effort": _env("QUICK_THINK_OPENAI_REASONING_EFFORT"),
    # Debate and discussion settings
    "max_debate_rounds": _env_int("MAX_DEBATE_ROUNDS", 1),
    "max_risk_discuss_rounds": _env_int("MAX_RISK_DISCUSS_ROUNDS", 1),
    "max_recur_limit": _env_int("MAX_RECUR_LIMIT", 100),
    # Data vendor configuration
    # Category-level configuration (default for all tools in category)
    "data_vendors": {
        "core_stock_apis": _env("VENDOR_CORE_STOCK_APIS", "yfinance"),
        "technical_indicators": _env("VENDOR_TECHNICAL_INDICATORS", "yfinance"),
        "fundamental_data": _env("VENDOR_FUNDAMENTAL_DATA", "yfinance"),
        "news_data": _env("VENDOR_NEWS_DATA", "yfinance"),
        "scanner_data": _env("VENDOR_SCANNER_DATA", "yfinance"),
    },
    # Tool-level configuration (takes precedence over category-level)
    "tool_vendors": {
        # Example: "get_stock_data": "alpha_vantage",  # Override category default
    },
}
