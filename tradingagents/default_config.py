import os

DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results"),
    "data_dir": "/Users/yluo/Documents/Code/ScAI/FR1-data",
    "data_cache_dir": os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
        "dataflows/data_cache",
    ),
    # LLM settings - Now provider-agnostic
    # Supported providers: openai, ollama, anthropic, google, azure, huggingface, groq, together, openrouter
    "llm_provider": "openai",  # Change this to switch providers
    "deep_think_llm": "o4-mini",  # Provider-specific model name
    "quick_think_llm": "gpt-4o-mini",  # Provider-specific model name
    "backend_url": "https://api.openai.com/v1",  # API endpoint (optional for some providers)
    "temperature": 0.7,  # Default temperature for LLM calls
    "llm_kwargs": {},  # Additional provider-specific parameters
    # Example configurations for different providers:
    # OpenAI: {"llm_provider": "openai", "backend_url": "https://api.openai.com/v1"}
    # Ollama: {"llm_provider": "ollama", "backend_url": "http://localhost:11434", "deep_think_llm": "llama3", "quick_think_llm": "llama3"}
    # Anthropic: {"llm_provider": "anthropic", "deep_think_llm": "claude-3-opus-20240229", "quick_think_llm": "claude-3-haiku-20240307"}
    # Google: {"llm_provider": "google", "deep_think_llm": "gemini-pro", "quick_think_llm": "gemini-pro"}
    # OpenRouter: {"llm_provider": "openrouter", "backend_url": "https://openrouter.ai/api/v1"}
    # Groq: {"llm_provider": "groq", "deep_think_llm": "mixtral-8x7b-32768", "quick_think_llm": "llama3-8b-8192"}
    # Debate and discussion settings
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,
    # Data vendor configuration
    # Category-level configuration (default for all tools in category)
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
