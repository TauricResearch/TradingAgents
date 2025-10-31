"""
Example configurations for different LLM providers.

Copy the configuration for your preferred provider and use it when
initializing TradingAgentsGraph.
"""

# ============================================================================
# OpenAI Configuration (Default)
# ============================================================================
OPENAI_CONFIG = {
    "llm_provider": "openai",
    "deep_think_llm": "gpt-4o",
    "quick_think_llm": "gpt-4o-mini",
    "backend_url": "https://api.openai.com/v1",
    "temperature": 0.7,
}

# ============================================================================
# Ollama Configuration (Local, Free)
# ============================================================================
OLLAMA_CONFIG = {
    "llm_provider": "ollama",
    "deep_think_llm": "llama3:70b",  # Or "llama3", "mistral", "mixtral", etc.
    "quick_think_llm": "llama3:8b",
    "backend_url": "http://localhost:11434",
    "temperature": 0.7,
}

# ============================================================================
# Anthropic Claude Configuration
# ============================================================================
ANTHROPIC_CONFIG = {
    "llm_provider": "anthropic",
    "deep_think_llm": "claude-3-opus-20240229",
    "quick_think_llm": "claude-3-haiku-20240307",
    "temperature": 0.7,
}

# ============================================================================
# Google Gemini Configuration
# ============================================================================
GOOGLE_CONFIG = {
    "llm_provider": "google",
    "deep_think_llm": "gemini-1.5-pro",
    "quick_think_llm": "gemini-1.5-flash",
    "temperature": 0.7,
}

# ============================================================================
# OpenRouter Configuration (Multi-Provider)
# ============================================================================
OPENROUTER_CONFIG = {
    "llm_provider": "openrouter",
    "deep_think_llm": "anthropic/claude-3-opus",
    "quick_think_llm": "anthropic/claude-3-haiku",
    "backend_url": "https://openrouter.ai/api/v1",
    "temperature": 0.7,
}

# ============================================================================
# Groq Configuration (Fast Inference)
# ============================================================================
GROQ_CONFIG = {
    "llm_provider": "groq",
    "deep_think_llm": "mixtral-8x7b-32768",
    "quick_think_llm": "llama3-8b-8192",
    "temperature": 0.7,
}

# ============================================================================
# Azure OpenAI Configuration
# ============================================================================
AZURE_CONFIG = {
    "llm_provider": "azure",
    "deep_think_llm": "gpt-4-deployment-name",  # Your deployment name
    "quick_think_llm": "gpt-35-turbo-deployment-name",  # Your deployment name
    "backend_url": "https://your-resource.openai.azure.com/",
    "temperature": 0.7,
    "llm_kwargs": {
        "api_version": "2024-02-01",
    }
}

# ============================================================================
# Together AI Configuration
# ============================================================================
TOGETHER_CONFIG = {
    "llm_provider": "together",
    "deep_think_llm": "meta-llama/Llama-3-70b-chat-hf",
    "quick_think_llm": "meta-llama/Llama-3-8b-chat-hf",
    "temperature": 0.7,
}

# ============================================================================
# Usage Example
# ============================================================================
if __name__ == "__main__":
    """
    Example of how to use these configurations.
    """
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.default_config import DEFAULT_CONFIG
    
    # Option 1: Use OpenAI (default)
    graph = TradingAgentsGraph(config=DEFAULT_CONFIG)
    
    # Option 2: Use Ollama (local)
    ollama_config = {**DEFAULT_CONFIG, **OLLAMA_CONFIG}
    graph = TradingAgentsGraph(config=ollama_config)
    
    # Option 3: Use Anthropic Claude
    anthropic_config = {**DEFAULT_CONFIG, **ANTHROPIC_CONFIG}
    graph = TradingAgentsGraph(config=anthropic_config)
    
    # Option 4: Use Google Gemini
    google_config = {**DEFAULT_CONFIG, **GOOGLE_CONFIG}
    graph = TradingAgentsGraph(config=google_config)
    
    # Option 5: Custom configuration
    custom_config = {
        **DEFAULT_CONFIG,
        "llm_provider": "ollama",
        "deep_think_llm": "llama3:70b",
        "quick_think_llm": "llama3:8b",
        "backend_url": "http://localhost:11434",
        "temperature": 0.5,  # Lower temperature for more deterministic outputs
        "max_debate_rounds": 2,
        "data_vendors": {
            "core_stock_apis": "yfinance",
            "technical_indicators": "yfinance",
            "fundamental_data": "alpha_vantage",
            "news_data": "alpha_vantage",
        },
    }
    graph = TradingAgentsGraph(config=custom_config)
