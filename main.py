import os
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from dotenv import load_dotenv

def run_analysis(config_overrides=None):
    """
    Initializes and runs a trading cycle with configurable overrides.
    """
    load_dotenv() # Load .env file variables

    config = DEFAULT_CONFIG.copy()

    # Override with environment variables if set
    config["llm_provider"] = os.environ.get("LLM_PROVIDER", config.get("llm_provider", "google"))
    config["backend_url"] = os.environ.get("LLM_BACKEND_URL", config.get("backend_url", "https://generativelanguage.googleapis.com/v1"))
    config["deep_think_llm"] = os.environ.get("LLM_DEEP_THINK_MODEL", config.get("deep_think_llm", "gemini-2.0-flash"))
    config["quick_think_llm"] = os.environ.get("LLM_QUICK_THINK_MODEL", config.get("quick_think_llm", "gemini-2.0-flash"))
    config["max_debate_rounds"] = int(os.environ.get("MAX_DEBATE_ROUNDS", config.get("max_debate_rounds", 1)))
    config["online_tools"] = os.environ.get("ONLINE_TOOLS", str(config.get("online_tools", True))).lower() == 'true'


    # Apply overrides from function argument
    if config_overrides:
        config.update(config_overrides)

    print("Using configuration:")
    for key, value in config.items():
        print(f"{key}: {value}")
        
    # Initialize with the final config
    ta = TradingAgentsGraph(debug=True, config=config)

    # Forward propagate
    _, decision = ta.propagate("NVDA", "2024-05-10")
    return decision

if __name__ == "__main__":
    # Example of running the trading analysis
    # You can override specific configurations here if needed, e.g.:
    # decision = run_trading_cyrun_analysiscle(config_overrides={"max_debate_rounds": 2})
    decision = run_analysis()
    print(decision)

    # Memorize mistakes and reflect
    # ta.reflect_and_remember(1000) # parameter is the position returns
