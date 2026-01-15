
import pandas as pd
import json
import logging
from typing import Dict, Any
from tradingagents.agents.analysts.market_analyst import create_market_analyst
from langchain_core.messages import AIMessage

# Mock LLM (We only care about the metric calculation logic, not the report generation)
class MockLLM:
    def invoke(self, input):
        return AIMessage(content="Analysis Complete.")

# Setup Logger
logging.basicConfig(level=logging.INFO)

# Mock Data (CSV Format as now enforced by alpaca.py)
MOCK_PRICE_CSV = """Date,Open,High,Low,Close,Volume
2025-01-01,100.0,105.0,99.0,102.0,1000000
2025-01-02,102.0,108.0,101.0,107.0,1500000
2025-01-03,107.0,110.0,106.0,109.0,2000000
2025-01-04,109.0,109.5,105.0,106.0,1200000
2025-01-05,106.0,107.0,104.0,105.0,1100000
2025-01-06,105.0,108.0,104.5,107.5,1300000
"""

# Mock Insider Data (YFinance CSV style)
MOCK_INSIDER_CSV = """
Share,Value,URL,Text,Transaction,Date
1000,150000,,Sale,Sale,2025-01-01
500,75000,,Purchase,Purchase,2025-01-01
"""

def test_market_analyst_parsing():
    print("--- TESTING MARKET ANALYST METRICS ---")
    
    # 1. Create Analyst Node
    analyst_node = create_market_analyst(MockLLM())
    
    # 2. Create State with Mock Ledger
    state = {
        "company_of_interest": "NVDA",
        "trade_date": "2026-01-15",
        "messages": [],
        "fact_ledger": {
            "ledger_id": "TEST_LEDGER_001",
            "price_data": MOCK_PRICE_CSV,  # Now passing CSV string!
            "insider_data": MOCK_INSIDER_CSV
        }
    }
    
    # 3. Run Node
    result = analyst_node(state)
    
    # 4. Verify Metrics
    print("\n--- RESULTS ---")
    print(f"Market Regime: {result['market_regime']}")
    print(f"Insider Net Flow: ${result['net_insider_flow']:,.2f}")
    print(f"Volatility Score: {result['volatility_score']}")
    
    # Assertions
    if "UNKNOWN" in result['market_regime']:
        print("❌ FAILURE: Regime Detection Failed (Still UNKNOWN)")
    else:
        print("✅ SUCCESS: Regime Detected")
        
    if result['net_insider_flow'] == 0.0:
         print("⚠️ WARNING: Insider Flow is 0.00 (Check calculation)")
    else:
         print(f"✅ SUCCESS: Insider Flow Calculated (${result['net_insider_flow']})")

if __name__ == "__main__":
    test_market_analyst_parsing()
