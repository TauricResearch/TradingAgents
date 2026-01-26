import os
from datetime import datetime
from typing import Dict

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

class TauricResearcher:
    """A trading research agent that analyzes stocks and makes trading decisions."""
    
    def __init__(self):
        """Initialize the TauricResearch agent and set up environment variables."""
        self.init_environ_vars()
    
    def init_environ_vars(self):
        """Initialize required API keys as environment variables."""
        os.environ["OPENAI_API_KEY"] = "sk-xxxx"  # IGNORE
        os.environ["ALPHA_VANTAGE_API_KEY"] = "J13IJQQOT4NLKF3A"
        os.environ["OLLAMA_API_KEY"] = "85a41aff1f814d3ca81f0a957ac02114.HGH8TZywvA0zbLe2y09Kvv4F"
            
    def run(self, stock_symbol: str = "NVDA", date: str = None, config: dict = DEFAULT_CONFIG.copy()) -> dict:
        """
        Run the trading agent to generate a trading decision for a stock.
        
        Args:
            config: Configuration dictionary for the trading graph (default: DEFAULT_CONFIG)
            
        Returns:
            The evaluated trading decision as a Python object.
        """
        # Initialize the trading graph with debug mode enabled
        ta = TradingAgentsGraph(debug=True, config=config)

        # Forward propagate through the graph to get trading decision for NVDA
        _, decision = ta.propagate(stock_symbol, date)
        decision = eval(decision)
        
        # Evaluate and return the decision string as a Python object
        return decision