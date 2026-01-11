
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from tradingagents.graph.trading_graph import TradingAgentsGraph

# Mock class to expose the method without full initialization
class MockGraph(TradingAgentsGraph):
    def __init__(self):
        # Skip super init to avoid API keys requirements
        self.ticker = "MOCK_TICKER"

def test_trend_override():
    print("🔍 TESTING TREND OVERRIDE LOGIC...")
    
    agent = MockGraph()
    
    # Test Case 1: PLTR Scenario (Sell in Bull Market)
    print("\n[TEST 1] PLTR Scenario: Sell signal in Bull Market")
    decision = "FINAL TRANSACTION PROPOSAL: SELL 75%"
    hard_data = {
        "status": "OK",
        "current_price": 185.0,
        "sma_200": 150.0,
        "revenue_growth": 0.62
    }
    regime = "TRENDING_UP"
    
    result = agent.apply_trend_override(decision, hard_data, regime)
    print(f"Input: {decision}")
    print(f"Regime: {regime}")
    if isinstance(result, dict) and result.get("action") == "HOLD":
        print("✅ PASS: Correctly recognized uptrend + growth to block SELL")
    else:
        print(f"❌ FAIL: Returned {result}")

    # Test Case 2: Volatile Regime (Should still protect leader)
    print("\n[TEST 2] Volatile Regime protection")
    regime = "VOLATILE"
    result = agent.apply_trend_override(decision, hard_data, regime)
    print(f"Regime: {regime}")
    if isinstance(result, dict) and result.get("action") == "HOLD":
         print("✅ PASS: Protected leader in VOLATILE regime")
    else:
         print(f"❌ FAIL: Returned {result}")

    # Test Case 3: Bear Market (Should allow sell)
    print("\n[TEST 3] Bear Market (Should allow SELL)")
    regime = "TRENDING_DOWN"
    result = agent.apply_trend_override(decision, hard_data, regime)
    print(f"Regime: {regime}")
    if result == decision:
         print("✅ PASS: Allowed SELL in Bear Market")
    else:
         print(f"❌ FAIL: Blocked SELL improperly: {result}")

    # Test Case 4: Low Growth (Should allow sell)
    print("\n[TEST 4] Low Growth (Should allow SELL)")
    hard_data["revenue_growth"] = 0.10
    regime = "TRENDING_UP"
    result = agent.apply_trend_override(decision, hard_data, regime)
    if result == decision:
         print("✅ PASS: Allowed SELL for low growth stock")
    else:
         print(f"❌ FAIL: Blocked SELL for low growth: {result}")

if __name__ == "__main__":
    test_trend_override()
