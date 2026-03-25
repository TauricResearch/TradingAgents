from copy import deepcopy
import os


def normalize_llm_routing(config):
    """Return config with llm_routing normalized to the expected dict shape."""
    normalized = deepcopy(config)
    llm_routing = normalized.get("llm_routing")

    if not isinstance(llm_routing, dict):
        normalized["llm_routing"] = {"default": {}, "roles": {}}
        return normalized

    default_route = llm_routing.get("default")
    role_routes = llm_routing.get("roles")
    normalized["llm_routing"] = {
        "default": deepcopy(default_route) if isinstance(default_route, dict) else {},
        "roles": deepcopy(role_routes) if isinstance(role_routes, dict) else {},
    }
    return normalized

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
    "quick_think_llm": "gpt-5-mini",
    "backend_url": "https://api.openai.com/v1",
    "llm_routing": None,
    "factor_rules_path": None,
    # Provider-specific thinking configuration
    "google_thinking_level": None,      # "high", "minimal", etc.
    "openai_reasoning_effort": None,    # "medium", "high", "low"
    "anthropic_effort": None,           # "high", "medium", "low"
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
    },
    # Tool-level configuration (takes precedence over category-level)
    "tool_vendors": {
        # Example: "get_stock_data": "alpha_vantage",  # Override category default
    },
}
