import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from tradingagents.agents.screening_agent import create_screening_agent
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

# Load environment variables
load_dotenv()

def main():
    print("--- Starting Market Screening ---")
    
    # 1. Initialize LLM for screening
    config = DEFAULT_CONFIG.copy()
    llm = ChatOpenAI(model=config["quick_think_llm"])
    
    # 2. Create and run Screening Agent
    screener = create_screening_agent(llm)
    
    # Initial state for screening
    state = {"messages": [HumanMessage(content="Find me the top gainers today and pick the most interesting one to analyze.")]}
    
    print("Running Screening Agent...")
    # In a real graph we would use langgraph, but here we can just invoke the node function for simplicity
    # or build a mini-graph. Let's just invoke the node loop manually for this demo.
    
    # Loop to handle multiple rounds of tool calls
    max_iterations = 5
    iteration = 0
    
    while iteration < max_iterations:
        iteration += 1
        
        # Invoke agent
        result = screener(state)
        state["messages"].extend(result["messages"])
        last_msg = result["messages"][-1]
        
        # Check if tool call
        if not last_msg.tool_calls:
            # No more tools, this is the final response
            print(f"Screening Agent Recommendation: {last_msg.content}")
            
            # Extract ticker (simple heuristic)
            import re
            tickers = re.findall(r'\b[A-Z]{2,5}\b', last_msg.content)
            
            if tickers:
                target_ticker = tickers[0] # Pick the first one
                print(f"Selected Ticker: {target_ticker}")
                
                # 3. Run TradingAgentsGraph on the selected ticker
                print(f"--- Starting Analysis for {target_ticker} ---")
                ta = TradingAgentsGraph(debug=True, config=config)
                
                from datetime import datetime
                today = datetime.now().strftime("%Y-%m-%d")
                
                _, decision = ta.propagate(target_ticker, today)
                print("\nFinal Decision:")
                print(decision)
            else:
                print("No tickers found in recommendation.")
            
            break
            
        else:
            print(f"Tool Call (Iter {iteration}): {last_msg.tool_calls}")
            
            # Execute tools
            from tradingagents.agents.utils.core_stock_tools import get_market_movers, get_earnings_calendar
            from tradingagents.agents.utils.news_data_tools import get_insider_transactions
            from tradingagents.agents.utils.technical_indicators_tools import get_indicators
            from tradingagents.dataflows.social_sentiment import get_trending_social
            
            tool_outputs = []
            for tool_call in last_msg.tool_calls:
                output = "Error: Tool not found"
                try:
                    if tool_call["name"] == "get_market_movers":
                        output = get_market_movers.invoke(tool_call["args"])
                    elif tool_call["name"] == "get_earnings_calendar":
                        output = get_earnings_calendar.invoke(tool_call["args"])
                    elif tool_call["name"] == "get_insider_transactions":
                        args = tool_call["args"]
                        if "curr_date" not in args:
                            from datetime import datetime
                            args["curr_date"] = datetime.now().strftime("%Y-%m-%d")
                        output = get_insider_transactions.invoke(args)
                    elif tool_call["name"] == "get_indicators":
                        args = tool_call["args"]
                        if "curr_date" not in args:
                            from datetime import datetime
                            args["curr_date"] = datetime.now().strftime("%Y-%m-%d")
                        output = get_indicators.invoke(args)
                    elif tool_call["name"] == "get_trending_social":
                        output = get_trending_social.invoke(tool_call["args"])
                except Exception as e:
                    output = f"Tool execution failed: {str(e)}"
                
                tool_outputs.append(
                    {"tool_call_id": tool_call["id"], "content": str(output)}
                )
            
            # Add tool outputs to messages
            from langchain_core.messages import ToolMessage
            for output in tool_outputs:
                state["messages"].append(ToolMessage(content=output["content"], tool_call_id=output["tool_call_id"]))

if __name__ == "__main__":
    main()
