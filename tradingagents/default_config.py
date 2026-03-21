import os

DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results"),
    "data_cache_dir": os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
        "dataflows/data_cache",
    ),
    # LLM settings
    "llm_provider": "openrouter",
    "deep_think_llm": "z-ai/glm-4.5-air:free",
    "quick_think_llm": "nvidia/nemotron-3-nano-30b-a3b:free",
    "backend_url": "https://openrouter.ai/api/v1",
    # Provider-specific thinking configuration
    "google_thinking_level": None,
    "openai_reasoning_effort": None,
    # Debate and discussion settings
    "max_debate_rounds": 1,        # 1 round = 3 turns in 3-way debate
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,
    # API keys (loaded from env)
    "tavily_api_key": os.getenv("TAVILY_API_KEY"),
    "twitter_bearer_token": os.getenv("TWITTER_BEARER_TOKEN"),
    "reddit_client_id": os.getenv("REDDIT_CLIENT_ID"),
    "reddit_client_secret": os.getenv("REDDIT_CLIENT_SECRET"),
    "polymarket_relayer_key": os.getenv("POLYMARKET_RELAYER_KEY"),
    # Auto-scan defaults
    "scan_defaults": {
        "min_volume_24h": 10000,
        "min_liquidity": 5000,
        "max_days_to_end": 30,
        "categories": [],
    },
}
