
import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv

sys.path.append(str(Path(__file__).parent.parent))

# Load env before imports
load_dotenv()

from langchain_core.runnables import Runnable
from langchain_core.messages import AIMessage
from tradingagents.agents.analysts.market_analyst import create_market_analyst

class MockLLM(Runnable):
    def bind_tools(self, tools, **kwargs):
        return self
    def invoke(self, input, config=None, **kwargs):
        return AIMessage(content="Mock Market Analysis Report")

def test_market_analyst_node():
    print("🔍 TESTING MARKET ANALYST NODE...")
    
    # 1. Setup
    mock_llm = MockLLM()
    market_analyst_node = create_market_analyst(mock_llm)
    
    # 2. Mock State
    state = {
        "company_of_interest": "PLTR",
        "trade_date": "2026-01-11",
        "messages": []
    }
    
    # 3. Execution
    print(f"   Executing node for {state['company_of_interest']}...")
    try:
        # Pass only state as fixed in previous steps
        result = market_analyst_node(state)
        
        # 4. Verification
        regime = result.get("market_regime")
        metrics = result.get("regime_metrics", {})
        
        print(f"📊 RESULTING REGIME: {regime}")
        print(f"   METRICS: {json.dumps(metrics, indent=2)}")
        
        if regime != "UNKNOWN" and metrics:
             print("✅ PASS: Regime detected correctly!")
        else:
             print("❌ FAIL: Regime is UNKNOWN or metrics missing.")
             
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_market_analyst_node()
