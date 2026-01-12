
import sys
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.append(str(Path(__file__).parent.parent))
os.environ["OPENAI_API_KEY"] = "sk-dummy"

from tradingagents.agents.analysts.market_analyst import create_market_analyst

def test_regime_end_to_end():
    print("🚀 TARGET: Verify Regime Error Propagation (Foolproof Test)")

    # 1. Setup Market Analyst with LLM
    mock_llm = MagicMock()
    market_analyst_func = create_market_analyst(mock_llm)
    
    # 2. Define State
    state = {
        "company_of_interest": "PLTR",
        "trade_date": "2026-01-11",
        "messages": []
    }
    
    print("\n[SCENARIO 1] Fatal Crash in Tool Setup (Previously Silent)")
    # We force a crash by mocking get_stock_data to Raise ERROR immediately
    # BUT wait, the 'tools' list in market_analyst.py uses the actual imported functions.
    # To cause a crash within the 'try' block but BEFORE the 'except', we can mock datetime or something fundamental.
    # Or simpler: We mock 'get_stock_data' to be something that crashes when 'invoke' is called.
    
    with patch("tradingagents.agents.analysts.market_analyst.get_stock_data") as mock_tool:
        # Make the tool invoke raise a standard Exception
        mock_tool.invoke.side_effect = RuntimeError("Simulated API Explosion")
        mock_tool.name = "get_stock_data" # Ensure it has a name so we don't crash on .name access
        
        # Run Node
        result = market_analyst_func(state)
        
        regime = result.get("market_regime")
        print(f"Outcome Regime: '{regime}'")
        
        if "Simulated API Explosion" in regime:
            print("✅ SUCCESS: Error caught and propagated!")
        elif "Fatal" in regime:
             print("✅ SUCCESS: Fatal error caught!")
        else:
            print(f"❌ FAILURE: Got '{regime}' instead of Error.")
            
    print("\n[SCENARIO 2] Silent Import Failure Simulation")
    # simulating if the internal logic fails drastically (e.g. tools list error)
    # We will mock 'get_stock_data' to NOT have a .name attribute.
    # This causes the list comprehension [t.name for t in tools] to CRASH.
    
    with patch("tradingagents.agents.analysts.market_analyst.get_stock_data") as mock_tool_broken:
        del mock_tool_broken.name # This forces AttributeError at line 98
        
        result_crash = market_analyst_func(state)
        regime_crash = result_crash.get("market_regime")
        print(f"Outcome Regime: '{regime_crash}'")
        
        if "Fatal" in regime_crash:
            print("✅ SUCCESS: Previously silent crash is now CAUGHT!")
        else:
             print(f"❌ FAILURE: Crash was swallowed? Got: {regime_crash}")

if __name__ == "__main__":
    test_regime_end_to_end()
