from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from typing import Callable


def create_screening_agent(llm: Callable) -> Callable:
    """
    Creates a screening agent node for the trading graph.
    Identifies potential stocks to analyze using market-wide screening techniques.
    
    Args:
        llm: Language model to use for analysis
    
    Returns:
        Callable agent node function that processes AgentState
    """
    
    def screening_agent_node(state: dict) -> dict:
        """
        Screening agent node.
        Scans the market for interesting stock candidates.
        
        Args:
            state: Current agent state containing:
                - messages: Conversation history
                - trade_date: Current trading date
        
        Returns:
            Updated state with screening recommendations
        """
        from tradingagents.agents.utils.agent_utils import (
            get_market_movers,
            get_earnings_calendar,
            get_insider_transactions,
            get_indicators,
            get_trending_social,
        )
        
        # Tools available to the screening agent
        tools = [
            get_market_movers,
            get_earnings_calendar,
            get_insider_transactions,
            get_indicators,
            get_trending_social,
        ]
        
        trade_date = state.get("trade_date", "")
        
        system_message = (
            f"You are a Market Screening Agent analyzing markets on {trade_date}. "
            "Your goal is to identify 'Hidden Gem' stocks efficiently."
            "\n\n"
            "**Instructions:**"
            "\n"
            "1. **Check Market Movers**: Use `get_market_movers` first."
            "\n"
            "2. **Quick Check**: If you see a promising ticker, verify it with ONE other tool (e.g., `get_trending_social` or `get_indicators`)."
            "\n"
            "3. **Decide Quickly**: Do not over-analyze. You have a STRICT limit of 3 tool calls. Once you have a candidate, STOP calling tools and output the recommendation."
            "\n"
            "4. **Emergency**: If you are unsure, just pick the top gainer from market movers. You MUST output a ticker."
            "\n\n"
            "**Deliverable:**"
            "\n"
            "Return candidates as a comma-separated list in the final line (e.g., 'NVDA, TSLA, AAPL')."
            "If you have enough information, output the list immediately."
        )
        
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant specialized in market analysis. "
                    "You have access to the following tools: {tool_names}.\n{system_message}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )
        
        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        
        # Bind tools to the LLM
        chain = prompt | llm.bind_tools(tools)
        
        # Initialize messages if needed
        if not state.get("messages"):
            state["messages"] = [("user", "Please screen the market and find interesting stock candidates to analyze.")]
        
        # Invoke the chain
        result = chain.invoke(state)
        
        # Add screening analysis to state
        return {
            "messages": state["messages"] + [result],
            "screening_report": result.content if hasattr(result, 'content') else str(result),
        }
    
    return screening_agent_node