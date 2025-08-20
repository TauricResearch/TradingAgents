from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Create a custom config
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "llamacpp"  # Use a different model
config["backend_url"] = "http://localhost:8080/v1"  # Use a different backend
config["deep_think_llm"] = (
    "models/Llama-3.3-70B-Instruct.Q5_K_M.gguf"  # Use a different model
)
config["quick_think_llm"] = (
    "models/Llama-3.3-70B-Instruct.Q5_K_M.gguf"  # Use a different model
)
config["max_debate_rounds"] = 1  # Increase debate rounds
config["online_tools"] = True  # Increase debate rounds

# Initialize with custom config
ta = TradingAgentsGraph(debug=True, config=config)

# forward propagate
_, decision = ta.propagate("AAPL", "2025-08-18")
print(decision)

# Memorize mistakes and reflect
# ta.reflect_and_remember(1000) # parameter is the position returns
