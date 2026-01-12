
import sys
import os
import json
from pathlib import Path
from unittest.mock import MagicMock

sys.path.append(str(Path(__file__).parent.parent))

# Set Dummy Key to bypass potential import checks (YFinance doesn't need it, but LangChain might)
os.environ["OPENAI_API_KEY"] = "sk-dummy"

from tradingagents.agents.analysts.market_analyst import create_market_analyst
from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable

class SpyLLM(Runnable):
    """A Mock LLM that behaves like a LangChain Runnable and prints inputs."""
    def __init__(self):
        self.captured_prompt = None

    def bind_tools(self, tools):
        # Return self so the chain 'prompt | llm.bind_tools(tools)' works
        print(f"\n🔗 SPY LLM: Tools bound successfully: {[t.name for t in tools]}")
        return self

    def invoke(self, input_val, config=None, **kwargs):
        # input_val might be a PromptValue or list of messages
        if hasattr(input_val, "to_messages"):
            messages = input_val.to_messages()
        else:
            messages = input_val
            
        print(f"\n🕵️  SPY LLM RECEIVED INPUT (Type: {type(input_val).__name__})")
        
        # Analyze the input messages
        for msg in messages:
            content = getattr(msg, "content", "")
            role = getattr(msg, "type", "unknown")
            
            debug_lower = content.lower()
            idx = debug_lower.find("regime detected")
            
            if idx != -1:
                self.captured_prompt = content
                print("\n[SYSTEM PROMPT CAPTURED]")
                print("="*60)
                # Print 200 chars around the hit
                start = max(0, idx - 100)
                end = min(len(content), idx + 300)
                print(f"...{content[start:end]}...")
                print("="*60)
            elif role == "system":
                 print(f"\n[SYSTEM MSG ({len(content)} chars)]: {content[:50]}... [SEARCH FAILED] ...{content[-50:]}")
                 print(f"   -> 'regime detected' index: {idx}")
        
        # Return a valid AIMessage to satisfy the node logic
        return AIMessage(content="[SPY LLM]: I have received the prompt. Data analysis complete.", tool_calls=[])

    def pipe(self, other):
        # Support pipe operator if needed
        return self

def verify_pltr_analyst_flow():
    print("🚀 STARTING PLTR PIPELINE AUDIT")
    print("   Goal: Run tools, Detect Regime, Verify Prompt Construction.")
    
    # 1. Setup Spy
    spy_llm = SpyLLM()
    market_analyst_node = create_market_analyst(spy_llm)
    
    # 2. Define State
    state = {
        "company_of_interest": "PLTR",
        "trade_date": "2026-01-11", # Future date to test Simulation Logic too?
        "messages": []
    }
    
    print(f"\n📊 INPUT STATE: Ticker={state['company_of_interest']}, Date={state['trade_date']}")
    
    # 3. Execution (Real Tool usage, Mocked LLM)
    print("\n... Running Node Logic (Fetching Data via YFinance)...")
    try:
        result = market_analyst_node(state)
        
        print("\n✅ NODE EXECUTION COMPLETE")
        print("\n📋 FINAL STATE OUTPUT:")
        print(f"   - Market Regime:    {result.get('market_regime')}")
        print(f"   - Broad Market:     {result.get('broad_market_regime')}")
        print(f"   - Volatility Score: {result.get('volatility_score')}")
        
        metrics = result.get('regime_metrics', {})
        print(f"   - Key Metrics:      {json.dumps(metrics, indent=2)}")
        
        if result.get('market_regime', '').startswith("UNKNOWN"):
            print("\n❌ FAILED: Regime is UNKNOWN. Check logs for warnings.")
        else:
            print("\n✅ PASSED: Regime detected successfully.")
            
    except Exception as e:
        print(f"\n💥 CRASHED: {e}")

if __name__ == "__main__":
    verify_pltr_analyst_flow()
