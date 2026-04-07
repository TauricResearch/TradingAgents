from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from dotenv import load_dotenv

if __name__ == "__main__":
    load_dotenv()
    ta = TradingAgentsGraph(debug=True, config=DEFAULT_CONFIG.copy())

    # forward propagate
    _, decision = ta.propagate("NVDA", "2026-01-15")
    print(decision)
    
    