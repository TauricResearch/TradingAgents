import re
from langchain_core.messages import HumanMessage, ToolMessage
from tradingagents.agents.utils.agent_states import AgentState

def parse_screening_output(state: AgentState):
    """
    Parses the output from the Screening Agent to extract the selected ticker.
    Updates the 'company_of_interest' in the state.
    """
    messages = state["messages"]
    last_message = messages[-1]
    content = last_message.content
    
    # Validation: If last message has tool calls, we MUST append a ToolMessage to satisfy the API
    params = {}
    if last_message.tool_calls:
        print("Screening Parser: Handling dangling tool call...")
        tool_messages = []
        for tool_call in last_message.tool_calls:
            tool_messages.append(
                ToolMessage(
                    tool_call_id=tool_call["id"],
                    content="Screening limit reached. Process terminated."
                )
            )
        # We need to return these messages to update the state
        # But we also need to return the ticker.
        # LangGraph merges dictionary updates.
        # But wait, we can just return {"messages": tool_messages, "company_of_interest": ...}
        params["messages"] = tool_messages

    
    # Simple regex to find tickers (uppercase letters, 2-5 chars)
    # This assumes the agent explicitly mentions the ticker in a standard format
    tickers = re.findall(r'\b[A-Z]{2,5}\b', content)
    
    if tickers:
        ticker = tickers[0]
        print(f"Screening Parser: Found ticker {ticker}")
        params["company_of_interest"] = ticker
        return params
    
    # Fallback: check previous AI messages if the last one was empty (e.g. tool call)
    print("Screening Parser: No ticker in last message, checking history...")
    for m in reversed(messages):
        if m.type == "ai" and m.content:
            tickers = re.findall(r'\b[A-Z]{2,5}\b', m.content)
            if tickers:
                ticker = tickers[0]
                print(f"Screening Parser: Found ticker in history: {ticker}")
                params["company_of_interest"] = ticker
                return params
                
    # Ultimate Fallback to prevent crash
    print("Screening Parser: No ticker found in history. Defaulting to NVDA.")
    params["company_of_interest"] = "NVDA"
    return params

def parse_pump_detection_output(state: AgentState):
    """
    Parses the output from the Pump Detection Agent to extract the selected ticker.
    Updates the 'company_of_interest' in the state.
    """
    messages = state["messages"]
    last_message = messages[-1]
    content = last_message.content
    
    params = {}
    if last_message.tool_calls:
        print("Pump Parser: Handling dangling tool call...")
        tool_messages = []
        for tool_call in last_message.tool_calls:
            tool_messages.append(
                ToolMessage(
                    tool_call_id=tool_call["id"],
                    content="Pump detection limit reached. Process terminated."
                )
            )
        params["messages"] = tool_messages
    
    # Similar logic for pump detection
    tickers = re.findall(r'\b[A-Z]{2,5}\b', content)
    
    if tickers:
        ticker = tickers[0]
        print(f"Pump Parser: Found ticker {ticker}")
        params["company_of_interest"] = ticker
        return params
    
    # Fallback checking history
    print("Pump Parser: No ticker in last message, checking history...")
    for m in reversed(messages):
        if m.type == "ai" and m.content:
            tickers = re.findall(r'\b[A-Z]{2,5}\b', m.content)
            if tickers:
                ticker = tickers[0]
                print(f"Pump Parser: Found ticker in history: {ticker}")
                params["company_of_interest"] = ticker
                return params

    print("Pump Parser: No ticker found. Defaulting to GME.")
    params["company_of_interest"] = "GME"
    return params
