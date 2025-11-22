import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
# Look for .env in the project root (parent of tradingagents directory)
project_root = Path(__file__).parent.parent
dotenv_path = project_root / ".env"
load_dotenv(dotenv_path=dotenv_path)

DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results"),
    "data_dir": "/Users/yluo/Documents/Code/ScAI/FR1-data",
    "data_cache_dir": os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
        "dataflows/data_cache",
    ),
    # LLM settings
    "llm_provider": "openai",
    "deep_think_llm": "o4-mini",
    "quick_think_llm": "gpt-4o-mini",
    "backend_url": "https://api.openai.com/v1",
    "openai_api_key": os.getenv("OPENAI_API_KEY"),  # Load from .env file
    # Sentiment analysis model (DAPTed Llama 3.1 8B)
    "use_dapt_sentiment": True,  # Use DAPTed model for sentiment analysis (set False to use OpenAI backup)
    # Path to DAPT PEFT adapter (dynamically uses current username)
    "dapt_adapter_path": f"/u/v/d/{os.getenv('USER', 'negi3')}/llama3_8b_dapt_transcripts_lora",
    # Fallback: OpenAI model if DAPT is unavailable
    "sentiment_fallback_llm": "o1-mini",  # OpenAI model for fallback
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
        # "get_stock_data": "alpha_vantage",  # Override category default
        "get_news": "alpha_vantage",   
        "get_global_news" :"openai"           # Override category default
    },
}
