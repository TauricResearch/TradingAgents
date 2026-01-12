
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

# FIX for API Key Error
import os 
os.environ["OPENAI_API_KEY"] = "sk-dummy"

from tradingagents.graph.trading_graph import TradingAgentsGraph
from enum import Enum

class MarketRegime(Enum):
    TRENDING_UP = "trending_up"
    VOLATILE = "volatile"
    BEAR = "bear"

def verify_override_logic():
    print("🚀 VERIFYING OVERRIDE LOGIC FIX...")
    
    graph = TradingAgentsGraph(selected_analysts=["market"])
    
    # Test Case: PLTR Scenario
    hard_data = {
        "current_price": 185.0,
        "sma_200": 153.0,
        "revenue_growth": 0.62, # 62%
        "status": "OK"
    }
    decision = "SELL 50% because valuation is insane."
    
    # 1. The Nightmare Type (Enum)
    print("\n[TEST] 1. Passing Raw Enum Object (MarketRegime.TRENDING_UP)")
    output = graph.apply_trend_override(decision, hard_data, MarketRegime.TRENDING_UP)
    
    # 2. The String
    print("\n[TEST] 2. Passing String ('trending_up')")
    output = graph.apply_trend_override(decision, hard_data, "trending_up")

if __name__ == "__main__":
    verify_override_logic()
