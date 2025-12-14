from datetime import datetime
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

# Load environment variables
load_dotenv()

# Patch failing tools
from langchain_core.tools import tool
import tradingagents.agents.utils.agent_utils as agent_utils

@tool
def mock_get_insider_transactions(ticker: str, curr_date: str = None):
    """Mock insider transactions."""
    return "Insider transactions: None significant."

@tool
def mock_get_indicators(ticker: str, curr_date: str = None):
    """Mock indicators."""
    return "Indicators: RSI 50, MACD positive."

@tool
def mock_get_market_movers():
    """Mock market movers."""
    return "Market Movers: NVDA +5%, TSLA -2%."

@tool
def mock_get_earnings_calendar(curr_date: str = None):
    """Mock earnings calendar."""
    return "Earnings: NVDA reporting soon."

@tool
def mock_get_trending_social():
    """Mock trending social."""
    return "Trending: NVDA, TSLA."

agent_utils.get_insider_transactions = mock_get_insider_transactions
agent_utils.get_indicators = mock_get_indicators
agent_utils.get_market_movers = mock_get_market_movers
agent_utils.get_earnings_calendar = mock_get_earnings_calendar
agent_utils.get_trending_social = mock_get_trending_social

def run_full_system():
    print("--- Starting Full Agent System ---")
    
    # Configure to use screening
    config = DEFAULT_CONFIG.copy()
    config["deep_think_llm"] = "gpt-4o-mini"
    config["quick_think_llm"] = "gpt-4o-mini"
    
    # Initialize graph with screening enabled
    print("Initializing TradingAgentsGraph with screening=True...")
    ta = TradingAgentsGraph(
        include_screening=True, 
        config=config,
        debug=True # Enable debug to see the trace
    )
    
    # Create initial state
    # We use a placeholder ticker since screening will find the real one
    trade_date = datetime.now().strftime("%Y-%m-%d")
    initial_state = ta.propagator.create_initial_state("PENDING", trade_date)
    
    # Override the initial message to trigger screening
    initial_state["messages"] = [HumanMessage(content="Find a promising stock to analyze based on today's market movers.")]
    
    print(f"Invoking graph with initial prompt: {initial_state['messages'][0].content}")
    
    # Run the graph
    # We use stream to see progress
    try:
        for chunk in ta.graph.stream(initial_state, config={"recursion_limit": 50}):
            for node, values in chunk.items():
                print(f"--- Node: {node} ---")
                if "messages" in values:
                    last_msg = values["messages"][-1]
                    if last_msg.content:
                        print(f"Output: {last_msg.content}")
                    if hasattr(last_msg, 'tool_calls') and last_msg.tool_calls:
                        for tc in last_msg.tool_calls:
                            print(f"Tool Call: {tc['name']} (Args: {tc['args']})")
                    
                if "company_of_interest" in values:
                    print(f"Current Ticker: {values['company_of_interest']}")
                    
        print("\n--- Execution Completed ---")
        
    except Exception as e:
        print(f"Execution failed: {e}")

if __name__ == "__main__":
    run_full_system()
