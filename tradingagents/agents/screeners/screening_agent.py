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
            "Your goal is to identify 'Hidden Gem' stocks before they make a massive move."
            "\n\n"
            "**Screening Strategy:**"
            "\n"
            "1. **Scan**: Use `get_market_movers` to find 'Most Active' or 'Top Losers' (potential reversals)"
            "\n"
            "2. **Social**: Use `get_trending_social` to find stocks buzzing on social platforms"
            "\n"
            "3. **Catalyst**: Use `get_earnings_calendar` to find upcoming catalysts"
            "\n"
            "4. **Smart Money**: Use `get_insider_transactions` to identify insider buying signals"
            "\n"
            "5. **Technicals**: Use `get_indicators` (RSI, MACD) to check for oversold conditions"
            "\n\n"
            "**Analysis Criteria:**"
            "\n"
            "Look for stocks that are:"
            "\n"
            "- Active but haven't spiked yet"
            "\n"
            "- Beaten down (in losers) with insider buying"
            "\n"
            "- Oversold (RSI < 30) for reversal potential"
            "\n"
            "- With upcoming catalysts (earnings, events)"
            "\n"
            "- With high social media buzz"
            "\n\n"
            "**Deliverable:**"
            "\n"
            "Analyze the market and recommend 1-3 ticker candidates for deeper analysis. "
            "Return candidates as a comma-separated list in the final line (e.g., 'NVDA, TSLA, AAPL')."
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