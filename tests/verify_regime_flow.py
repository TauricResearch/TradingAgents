
import sys
import os
import pandas as pd
from unittest.mock import MagicMock, patch
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
os.environ["OPENAI_API_KEY"] = "sk-dummy"

from tradingagents.agents.analysts.market_analyst import create_market_analyst

def verify_regime_flow():
    print("🚀 VERIFYING DATA FLOW TO REGIME DETECTOR...")
    
    # Mock LLM
    mock_llm = MagicMock()
    mock_llm.bind_tools.return_value.invoke.return_value.tool_calls = []
    mock_llm.bind_tools.return_value.invoke.return_value.content = "Analysis Report"
    
    # Create Node
    analyst_node = create_market_analyst(mock_llm)
    
    # Mock State
    state = {
        "company_of_interest": "PLTR",
        "trade_date": "2026-01-11",
        "messages": []
    }
    
    # Mock CSV Return
    mock_csv = """Date,Close
2025-01-01,100
2025-01-02,105
2025-01-03,110
2025-01-04,115
2025-01-05,120
2025-01-06,125
"""
    
    with patch("tradingagents.agents.analysts.market_analyst.get_stock_data") as mock_tool:
        # Side effect to return mocked CSV
        mock_tool.invoke.return_value = mock_csv
        mock_tool.name = "get_stock_data"
        
        # Also need to mock SPY data or it will try to fetch it
        # Actually SPY fetch is inside a try/except so if it fails it's fine, but let's mock it to be clean
        # Wait, get_stock_data is called twice. Once for Ticker, once for SPY.
        # We can use side_effect with a function to return based on input
        
        def side_effect(args):
            symbol = args.get("symbol")
            if symbol == "SPY":
                return mock_csv # Spy data
            return mock_csv # Target data
            
        mock_tool.invoke.side_effect = side_effect
        
        print("\n[TEST] Calling Market Analyst Node...")
        
        # We rely on the internal LOGGER to print our debug message:
        # "DEBUG: Passing prices to detector. Type: <class 'pandas.core.series.Series'>, Length: 6"
        
        result = analyst_node(state)
        
        print(f"\n[RESULT] Market Regime: {result.get('market_regime')}")
        print(f"[RESULT] Volatility: {result.get('volatility_score')}")
        
        if "UNKNOWN" not in result.get("market_regime", "UNKNOWN"):
            print("✅ SUCCESS: Regime detected successfully.")
        else:
            print("❌ FAILURE: Regime is still UNKNOWN.")

if __name__ == "__main__":
    verify_regime_flow()
