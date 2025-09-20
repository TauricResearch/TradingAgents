import os

DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(
        os.path.join(os.path.dirname(__file__), ".")
    ),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results"),
    "data_dir": "/Users/yluo/Documents/Code/ScAI/FR1-data",
    "data_cache_dir": os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
        "dataflows/data_cache",
    ),
    "llm_provider": "openai",
    "deep_think_llm": "o1-mini",
    "quick_think_llm": "gpt-4o-mini",
    "backend_url": "https://api.openai.com/v1",
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,
    "online_tools": True,
}

OPENAI_MODELS = {
    "reasoning": ["o1", "o1-mini", "o3", "o3-mini"],
    "flagship": ["gpt-4o", "gpt-4o-mini"],
    "latest": ["gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano"],
}

ANTHROPIC_MODELS = {
    "opus": [
        "claude-3-opus-20240229", "claude-opus-4", "claude-opus-4.1"
    ],
    "sonnet": [
        "claude-3-5-sonnet-20241022",
        "claude-sonnet-4",
        "claude-3.7-sonnet"
    ],
    "haiku": ["claude-3-haiku-20240307", "claude-3-5-haiku-20241022"]
}
