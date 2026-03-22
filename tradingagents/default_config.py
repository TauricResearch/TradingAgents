import os

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
    # Provider-specific thinking configuration
    "google_thinking_level": None, # "high", "minimal", etc.
    "openai_reasoning_effort": None, # "medium", "high", "low"
    # Debate and discussion settings
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,
    # Data vendor configuration (Stock/TradFi)
    "data_vendors": {
        "core_stock_apis": "yfinance", # Options: alpha_vantage, yfinance
        "technical_indicators": "yfinance", # Options: alpha_vantage, yfinance
        "fundamental_data": "yfinance", # Options: alpha_vantage, yfinance
        "news_data": "yfinance", # Options: alpha_vantage, yfinance
        # DEX/Crypto data vendors (Phase 1-3)
        "core_token_apis": "coingecko",
        "token_info": "coingecko",
        "technical_indicators_dex": "coingecko",
        "defi_fundamentals": "defillama",  # Phase 2
        "whale_tracking": "birdeye",  # Phase 3
    },
    # Tool-level configuration (takes precedence over category-level)
    "tool_vendors": {
        # Example: "get_stock_data": "alpha_vantage", # Override category default
    },
    # Trading mode: "stock" (TradFi) or "dex" (DeFi/Crypto)
    "trading_mode": "stock",
    # Default blockchain for DEX operations
    "default_chain": "solana",  # Options: solana, ethereum, bsc, arbitrum, etc.
}