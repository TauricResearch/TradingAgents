
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.append(str(Path(__file__).parent.parent))
os.environ["OPENAI_API_KEY"] = "sk-dummy"

from tradingagents.agents.analysts.market_analyst import create_market_analyst

def test_market_analyst_logic():
    print("🚀 TESTING MARKET ANALYST LOGIC")
    
    # Mock state
    state = {
        "company_of_interest": "PLTR",
        "trade_date": "2026-01-11",
        "market_report": "",
        "messages": []
    }
    
    # Mock LLM since create_market_analyst requires it
    mock_llm_main = MagicMock()
    market_analyst_node = create_market_analyst(mock_llm_main)
    
    # 1. Mock get_stock_data to FAIL
    with patch("tradingagents.agents.analysts.market_analyst.get_stock_data") as mock_tool:
        mock_tool.invoke.side_effect = Exception("API Timeout")
        
        # We also need to mock the LLM because it's called
        # But wait, the LLM is inside the node logic? No, the node calls llm.invoke
        # Actually market_analyst_node takes (state, name, llm) or creates it?
        # It's a partial. `create_market_analyst_node` returns the function.
        # But `market_analyst.py` has `market_analyst_node(state, name, llm)`.
        
        # Wait, how is it defined?
        # def market_analyst_node(state, name, llm=None): ...
        
        # I need to pass a mock LLM
        mock_llm = MagicMock()
        mock_llm.invoke.return_value.content = "Mock Report"
        
        print("\n[TEST] 1. Simulating Data Fetch Crash...")
        try:
            # The inner function only takes 'state'
            result = market_analyst_node(state)
            regime = result.get("market_regime")
            print(f"Result: {regime}")
        except Exception as e:
            print(f"CRASHED: {e}")

if __name__ == "__main__":
    test_market_analyst_logic()
