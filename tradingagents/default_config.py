import os

DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results"),
    #"data_dir": "/Users/yluo/Documents/Code/ScAI/FR1-data",
    "data_dir" : os.path.join("project_dir","data",),
    "data_cache_dir": os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
        "dataflows/data_cache",
    ),
    # LLM settings
    #"llm_provider": "openai",
    #"deep_think_llm": "o4-mini",
    #"quick_think_llm": "gpt-4o-mini",
    #"backend_url": "https://api.openai.com/v1",
    # Debate and discussion settings
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 500, #100
    # Data vendor configuration
    # Category-level configuration (default for all tools in category)
    
    # Default LLM is set to local LMStudio instance
    "llm_provider": "lmstudio",
    "deep_think_llm": "glm-4.7-reap-50-mixed-3-4-bits",
    "quick_think_llm": "qwen/qwen3-vl-30b",
    "backend_url": "http://192.168.0.20:1234/v1",
    "api_key": "blablabla",

    "local_url": "http://192.168.0.20:1234/v1",
    "ollama_url":"http://192.168.0.20:11434/v1",

    "nvidia_backend_url" : "https://integrate.api.nvidia.com/v1",
    "nvidia_api_key" : "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",
    
    
    "data_vendors": {
        "core_stock_apis": "yfinance",       # Options: yfinance, alpha_vantage, local
        "technical_indicators": "yfinance",  # Options: yfinance, alpha_vantage, local
        "fundamental_data": "alpha_vantage", # Options: openai, alpha_vantage, local
        "news_data": "alpha_vantage",        # Options: openai, alpha_vantage, google, local
    },
    # Tool-level configuration (takes precedence over category-level)
    "tool_vendors": {
        # Example: "get_stock_data": "alpha_vantage",  # Override category default
        # Example: "get_news": "openai",               # Override category default
    },
}
