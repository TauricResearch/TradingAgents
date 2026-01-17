import os

DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results"),
    "data_dir": "/Users/yluo/Documents/Code/ScAI/FR1-data",
    "data_cache_dir": os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
        "dataflows/data_cache",
    ),
    # LLM settings
    #"llm_provider": "openai",
    #"deep_think_llm": "o4-mini",
    #"quick_think_llm": "gpt-4o-mini",
    #"backend_url": "https://api.openai.com/v1",
    
    # Default LLM is set to local LMStudio instance
    "llm_provider": "lmstudio",
    "deep_think_llm": "glm-4.7-reap-50-mixed-3-4-bits",
    "quick_think_llm": "qwen/qwen3-vl-30b",
    "backend_url": "http://192.168.0.20/v1",
    "api_key": "blablabla",
    
    # Debate and discussion settings
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,
    # Tool settings
    "online_tools": True,
}
