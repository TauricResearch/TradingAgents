import json
import os
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.json"
with CONFIG_PATH.open("r", encoding="utf-8") as config_file:
    CONFIG = json.load(config_file)

DEFAULT_LLM_SETTINGS = CONFIG.get("DEFAULT_LLM_SETTINGS", {})
BASE_URLS = {display.lower(): url for display, url in CONFIG.get("BASE_URLS", [])}
DEFAULT_PROVIDER = DEFAULT_LLM_SETTINGS.get("llm_provider", "openai").lower()
DEFAULT_BACKEND_URL = BASE_URLS.get(
    DEFAULT_PROVIDER, BASE_URLS.get("openai", "https://api.openai.com/v1")
)

DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results"),
    "data_cache_dir": os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
        "dataflows/data_cache",
    ),
    # LLM settings
    "llm_provider": DEFAULT_PROVIDER,
    "deep_think_llm": DEFAULT_LLM_SETTINGS.get("deep_think_llm", "gpt-5.2"),
    "quick_think_llm": DEFAULT_LLM_SETTINGS.get("quick_think_llm", "gpt-5-mini"),
    "backend_url": DEFAULT_BACKEND_URL,
    # Provider-specific thinking configuration
    "google_thinking_level": None,      # "high", "minimal", etc.
    "openai_reasoning_effort": None,    # "medium", "high", "low"
    "anthropic_effort": None,           # "high", "medium", "low"
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
    },
    # Tool-level configuration (takes precedence over category-level)
    "tool_vendors": {
        # Example: "get_stock_data": "alpha_vantage",  # Override category default
    },
}
