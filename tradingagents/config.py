"""
Configuration management for TradingAgents.
Loads configuration from environment variables and .env file.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env file from project root
project_root = Path(__file__).parent.parent
env_path = project_root / ".env"
load_dotenv(env_path)


def get_config():
    """Get configuration with environment variable overrides."""
    config = {
        # Project directories
        "project_dir": str(project_root / "tradingagents"),
        "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results"),
        "data_dir": os.getenv(
            "TRADINGAGENTS_DATA_DIR",
            "/Users/yluo/Documents/Code/ScAI/FR1-data",
        ),
        "data_cache_dir": str(
            project_root / "tradingagents" / "dataflows" / "data_cache",
        ),
        # LLM settings
        "llm_provider": os.getenv("LLM_PROVIDER", "openai"),
        "deep_think_llm": os.getenv("DEEP_THINK_LLM", "o4-mini"),
        "quick_think_llm": os.getenv("QUICK_THINK_LLM", "gpt-4o-mini"),
        "backend_url": os.getenv("BACKEND_URL", "https://api.openai.com/v1"),
        # Debate and discussion settings
        "max_debate_rounds": int(os.getenv("MAX_DEBATE_ROUNDS", "1")),
        "max_risk_discuss_rounds": int(os.getenv("MAX_RISK_DISCUSS_ROUNDS", "1")),
        "max_recur_limit": int(os.getenv("MAX_RECUR_LIMIT", "100")),
        # Tool settings
        "online_tools": os.getenv("ONLINE_TOOLS", "true").lower() == "true",
        # API Keys (loaded from environment)
        "openai_api_key": os.getenv("OPENAI_API_KEY"),
        "finnhub_api_key": os.getenv("FINNHUB_API_KEY"),
        "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY"),
        "google_api_key": os.getenv("GOOGLE_API_KEY"),
        "reddit_client_id": os.getenv("REDDIT_CLIENT_ID"),
        "reddit_client_secret": os.getenv("REDDIT_CLIENT_SECRET"),
    }

    # Validate required API keys based on provider
    if config["llm_provider"] == "openai" and not config["openai_api_key"]:
        msg = "OPENAI_API_KEY is required when using OpenAI provider"
        raise ValueError(msg)
    if config["llm_provider"] == "anthropic" and not config["anthropic_api_key"]:
        msg = "ANTHROPIC_API_KEY is required when using Anthropic provider"
        raise ValueError(msg)
    if config["llm_provider"] == "google" and not config["google_api_key"]:
        msg = "GOOGLE_API_KEY is required when using Google provider"
        raise ValueError(msg)

    if not config["finnhub_api_key"]:
        pass

    return config


# Export default configuration
DEFAULT_CONFIG = get_config()
