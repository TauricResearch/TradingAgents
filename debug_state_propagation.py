import asyncio
import logging
import os
import sys

# Ensure we can import from the project root
sys.path.append(os.getcwd())

from agent_os.backend.services.langgraph_engine import LangGraphEngine

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("debug_state")

async def debug_run():
    LangGraphEngine()
    
    # We'll run a mock pipeline first to see how it streams
    print("--- Running Mock Pipeline ---")
    run_id = "test_mock_run"
    params = {
        "mock_type": "pipeline",
        "ticker": "AAPL",
        "date": "2026-04-06",
        "speed": 10.0
    }
    
    from agent_os.backend.services.mock_engine import MockEngine
    mock_engine = MockEngine()
    
    async for event in mock_engine.run_mock(run_id, params):
        print(f"Event: {event.get('type')} from {event.get('agent')} ({event.get('node_id')})")
        if event.get('type') == 'result':
             print(f"  Message: {event.get('message')}")

    print("\n--- Running Real Pipeline with Mock LLM (if possible) ---")
    # For a real pipeline, we'd need valid API keys or a mock LLM.
    # Let's try to mock the LLM in the config.
    
    # Actually, let's just inspect how LangGraphEngine.run_pipeline handles the state.
    # It uses TradingAgentsGraph internally.
    
    # To really "debug if information is saved in correct states", 
    # we should look at how it saves to disk.
    
    run_id = "debug_pipeline_run"
    params = {
        "ticker": "AAPL",
        "date": "2026-04-06",
        "run_id": run_id
    }
    
    # Instead of running the whole thing (which needs LLM), 
    # let's inspect the `TradingAgentsGraph` initialization and state creation.
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    
    graph_wrapper = TradingAgentsGraph(selected_analysts=["market", "news"])
    initial_state = graph_wrapper.propagator.create_initial_state(
        "AAPL", "2026-04-06", run_id=run_id
    )
    
    print(f"Initial State Keys: {list(initial_state.keys())}")
    print(f"Scanner Context: '{initial_state.get('scanner_context_packet')}'")
    
    # Let's see if we can manually trigger a node
    # We'll need to mock the LLM for the node
    from langchain_core.messages import AIMessage
    from langchain_core.runnables import Runnable

    from tradingagents.agents.analysts.market_analyst import create_market_analyst
    
    class MockLLM(Runnable):
        def __init__(self, response_text):
            self.response_text = response_text
            self.last_prompt = None
        
        def invoke(self, prompt, *args, **kwargs):
            self.last_prompt = prompt
            return AIMessage(
                content=self.response_text,
                usage_metadata={'input_tokens': 10, 'output_tokens': 5, 'total_tokens': 15},
                response_metadata={'model_name': 'mock-model'}
            )
        
        def bind(self, *args, **kwargs):
            return self
        
        # Required for Runnable
        def stream(self, input, config=None, **kwargs):
             yield self.invoke(input, config=config, **kwargs)

    mock_llm = MockLLM("- Market is bullish at $190.\n- Strong momentum +5%.\n\n| Level | Value |\n|---|---|\n| Resistance | $195 |\n")
    market_analyst_node = create_market_analyst(mock_llm)
    
    # Prepare state for market analyst
    state = initial_state.copy()
    
    print("Executing Market Analyst node...")
    result = market_analyst_node(state)
    print(f"Market Analyst result keys: {list(result.keys())}")
    print(f"Market Report: {result['market_report']}")
    
    # Now check if downstream can reach it.
    # Update state with market analyst result
    state.update(result)
    
    from unittest.mock import MagicMock

    from tradingagents.agents.managers.research_manager import create_research_manager
    
    # Update mock for Research Manager
    mock_llm.response_text = "- Recommendation: BUY (HIGH)\n- Rationale: Market is bullish at $190 (MED)\n- Strategic Action: Entry at $192 (LOW)"
    research_manager_node = create_research_manager(mock_llm, MagicMock())
    
    print("Executing Research Manager node...")
    result_rm = research_manager_node(state)
    print(f"Research Manager result keys: {list(result_rm.keys())}")
    
    # Check if research manager's prompt included market report
    prompt_text = str(mock_llm.last_prompt)
    print(f"Research Manager prompt contains 'Market is bullish at $190': {'Market is bullish at $190' in prompt_text}")

    # Verify structured output propagation in detail
    market_struct = state.get('market_report_structured', {})
    print(f"Market Structured - Ticker: {market_struct.get('ticker')}")
    print(f"Market Structured - Status: {market_struct.get('status')}")
    print(f"Market Structured - Macro Regime: {market_struct.get('macro_regime')}")
    # Since our mock response was "Market is bullish", it doesn't have prices or bullets
    print(f"Market Structured - Numeric Mentions: {market_struct.get('key_metrics', {}).get('numeric_mentions')}")
    
    rm_struct = result_rm.get('investment_plan_structured', {})
    print(f"RM Structured - Ticker: {rm_struct.get('ticker')}")
    print(f"RM Structured - Recommendation: {rm_struct.get('recommendation')}")
    print(f"RM Structured - Confidence (High): {rm_struct.get('key_metrics', {}).get('high_confidence_claims')}")

if __name__ == "__main__":
    asyncio.run(debug_run())
