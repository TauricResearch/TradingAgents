import json
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig

from tradingagents.agents.utils.agent_states import AgentState
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
)
from tradingagents.agents.utils.review_tools import get_past_performance_data

def create_review_analyst(llm):
    """Create the Performance Review Analyst agent."""
    
    # Bind the review tool to the LLM
    llm_with_tools = llm.bind_tools([get_past_performance_data])
    
    def review_analyst(state: AgentState, config: RunnableConfig):
        """Analyze past predictions and compare with current performance."""
        ticker = state.get("company_of_interest", "Unknown")
        asset_type = state.get("asset_type", "stock")
        context_str = build_instrument_context(ticker, asset_type)
        curr_date = state.get("trade_date")

        system_message = (
            "You are a Performance Review Analyst for a hedge fund. Your job is to evaluate the system's past predictions (hindsight analysis).\n"
            f"You MUST use the 'get_past_performance_data' tool with the ticker '{ticker}' and the current simulated date '{curr_date}' (as the 'curr_date' parameter) to retrieve the system's previous analysis and the actual stock price performance since that date.\n\n"
            "If the tool returns no past data, simply state: 'No past analysis data available for hindsight review.' and stop.\n"
            "If past data is found:\n"
            "1. Read the past Trader Plan and final decision.\n"
            "2. Compare it with the actual Return (%) since that date.\n"
            "3. Provide a critical critique: Was the system right or wrong? What risks did it miss or correctly identify?\n"
            "4. Conclude with a 'Lessons Learned' section for the current trading day.\n"
            "Do NOT provide a new trading decision for today, ONLY review the past.\n\n"
            f"{context_str}\n"
            + get_language_instruction()
        )
        
        messages = [
            SystemMessage(content=system_message),
            *state["messages"],
        ]
        
        response = llm_with_tools.invoke(messages, config)
        return {"messages": [response], "sender": "Review Analyst"}
        
    return review_analyst
