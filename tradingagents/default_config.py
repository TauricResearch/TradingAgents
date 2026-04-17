import copy
import os
from pathlib import Path

_MINIMAX_ANTHROPIC_BASE_URL = "https://api.minimaxi.com/anthropic"
_MINIMAX_DEFAULT_TIMEOUT_SECS = 60.0
_MINIMAX_DEFAULT_MAX_RETRIES = 1
_MINIMAX_DEFAULT_EXTRA_RETRY_ATTEMPTS = 2
_MINIMAX_DEFAULT_RETRY_BASE_DELAY_SECS = 1.5
_MINIMAX_DEFAULT_ANALYST_NODE_TIMEOUT_SECS = 75.0

_TRADINGAGENTS_HOME = os.path.join(os.path.expanduser("~"), ".tradingagents")

DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", os.path.join(_TRADINGAGENTS_HOME, "logs")),
    "data_cache_dir": os.getenv("TRADINGAGENTS_CACHE_DIR", os.path.join(_TRADINGAGENTS_HOME, "cache")),
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
    # Optional runtime context for account-aware and peer-aware decisions
    "portfolio_context": "",
    "peer_context": "",
    "peer_context_mode": "UNSPECIFIED",
    # Debate and discussion settings
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,
    "research_node_timeout_secs": 90.0,  # Increased for parallel subagent architecture with slow LLM
    # Data vendor configuration
    # Category-level configuration (default for all tools in category)
    "data_vendors": {
        "core_stock_apis": "yfinance",       # Options: alpha_vantage, yfinance
        "technical_indicators": "yfinance",  # Options: alpha_vantage, yfinance
        "fundamental_data": "yfinance",      # Options: alpha_vantage, yfinance
        "news_data": "yfinance",             # Options: alpha_vantage, yfinance
    },
    # Tool-level configuration (takes precedence over category-level)
    "tool_vendors": {
        # Example: "get_stock_data": "alpha_vantage",  # Override category default
    },
}


def _looks_like_minimax_anthropic(provider: str | None, backend_url: str | None) -> bool:
    return (
        str(provider or "").lower() == "anthropic"
        and _MINIMAX_ANTHROPIC_BASE_URL in str(backend_url or "").lower()
    )


def normalize_runtime_llm_config(config: dict) -> dict:
    """Normalize runtime LLM settings for known provider/backend quirks."""
    normalized = copy.deepcopy(config)
    provider = normalized.get("llm_provider")
    backend_url = normalized.get("backend_url")

    if _looks_like_minimax_anthropic(provider, backend_url):
        normalized["backend_url"] = _MINIMAX_ANTHROPIC_BASE_URL
        if not normalized.get("llm_timeout"):
            normalized["llm_timeout"] = _MINIMAX_DEFAULT_TIMEOUT_SECS
        if normalized.get("llm_max_retries") in (None, 0):
            normalized["llm_max_retries"] = _MINIMAX_DEFAULT_MAX_RETRIES
        if not normalized.get("minimax_retry_attempts"):
            normalized["minimax_retry_attempts"] = _MINIMAX_DEFAULT_EXTRA_RETRY_ATTEMPTS
        if not normalized.get("minimax_retry_base_delay"):
            normalized["minimax_retry_base_delay"] = _MINIMAX_DEFAULT_RETRY_BASE_DELAY_SECS
        if not normalized.get("analyst_node_timeout_secs"):
            normalized["analyst_node_timeout_secs"] = _MINIMAX_DEFAULT_ANALYST_NODE_TIMEOUT_SECS

    return normalized


def _resolve_runtime_llm_overrides() -> dict:
    """Resolve provider/model/base URL overrides from the current environment."""
    overrides: dict[str, object] = {}

    provider = os.getenv("TRADINGAGENTS_LLM_PROVIDER")
    if not provider:
        if os.getenv("ANTHROPIC_BASE_URL"):
            provider = "anthropic"
        elif os.getenv("OPENAI_BASE_URL"):
            provider = "openai"
    if provider:
        overrides["llm_provider"] = provider

    backend_url = (
        os.getenv("TRADINGAGENTS_BACKEND_URL")
        or os.getenv("ANTHROPIC_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
    )
    if backend_url:
        overrides["backend_url"] = backend_url

    shared_model = os.getenv("TRADINGAGENTS_MODEL")
    deep_model = os.getenv("TRADINGAGENTS_DEEP_MODEL") or shared_model
    quick_model = os.getenv("TRADINGAGENTS_QUICK_MODEL") or shared_model
    if deep_model:
        overrides["deep_think_llm"] = deep_model
    if quick_model:
        overrides["quick_think_llm"] = quick_model

    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("MINIMAX_API_KEY")
    if anthropic_api_key:
        overrides["api_key"] = anthropic_api_key

    portfolio_context = os.getenv("TRADINGAGENTS_PORTFOLIO_CONTEXT")
    if portfolio_context is not None:
        overrides["portfolio_context"] = portfolio_context

    peer_context = os.getenv("TRADINGAGENTS_PEER_CONTEXT")
    if peer_context is not None:
        overrides["peer_context"] = peer_context

    peer_context_mode = os.getenv("TRADINGAGENTS_PEER_CONTEXT_MODE")
    if peer_context_mode is not None:
        overrides["peer_context_mode"] = peer_context_mode

    return overrides


def load_project_env(start_path):
    """Load the nearest .env from the given path upward."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return None

    current = Path(start_path).resolve()
    if current.is_file():
        current = current.parent

    for directory in (current, *current.parents):
        env_path = directory / ".env"
        if env_path.exists():
            # Project entrypoints should use the repo-local runtime settings even
            # when the user's shell exports unrelated Anthropic/OpenAI variables.
            load_dotenv(env_path, override=True)
            return env_path
    return None


def get_default_config():
    config = copy.deepcopy(DEFAULT_CONFIG)
    config.update(_resolve_runtime_llm_overrides())
    return normalize_runtime_llm_config(config)
