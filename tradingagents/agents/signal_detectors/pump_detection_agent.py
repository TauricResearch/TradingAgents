"""
Pump Detection Agent
Analyzes stocks for potential pump signals and pre-pump opportunities.
Integrates into the langgraph agentic architecture.
"""

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from typing import Callable


def create_pump_detection_agent(llm: Callable) -> Callable:
    """
    Creates a pump detection agent node for the trading graph.
    Identifies stocks likely to experience pump moves using 5 detection signals.
    
    Args:
        llm: Language model to use for analysis
    
    Returns:
        Callable agent node function that processes AgentState
    """
    
    def pump_detection_node(state: dict) -> dict:
        """
        Pump detection agent node.
        Analyzes a given stock for pump probability signals.
        
        Args:
            state: Current agent state containing:
                - messages: Conversation history
                - company_of_interest: Stock ticker to analyze
                - trade_date: Current trading date
        
        Returns:
            Updated state with pump analysis results
        """
        from tradingagents.agents.utils.pump_detection_tools import (
            detect_volume_spike,
            detect_price_acceleration,
            detect_social_sentiment_surge,
            detect_oversold_bounce,
            detect_catalyst_event,
            calculate_pump_score,
        )
        
        # Tools available to the pump detection agent
        tools = [
            detect_volume_spike,
            detect_price_acceleration,
            detect_social_sentiment_surge,
            detect_oversold_bounce,
            detect_catalyst_event,
            calculate_pump_score,
        ]
        
        ticker = state.get("company_of_interest", "")
        trade_date = state.get("trade_date", "")
        
        system_message = (
            f"You are a Pump Detection Specialist analyzing {ticker} on {trade_date}. "
            "Your goal is to identify if this stock is likely to experience sudden price increases (pumps)."
            "\n\n"
            "**Pump Detection Analysis:**"
            "\n"
            "Run these detection tools in order:"
            "\n"
            "1. Use `detect_volume_spike` - Find abnormal trading volume (2x+ average)"
            "\n"
            "2. Use `detect_price_acceleration` - Check for rapid price gains"
            "\n"
            "3. Use `detect_social_sentiment_surge` - Scan for social media buzz"
            "\n"
            "4. Use `detect_oversold_bounce` - Check technical oversold setup (RSI < 30)"
            "\n"
            "5. Use `detect_catalyst_event` - Find upcoming catalysts"
            "\n"
            "6. Use `calculate_pump_score` - Combine all signals into final pump score"
            "\n\n"
            "**Scoring Guide:**"
            "\n"
            "- 70+: 🔴 VERY HIGH pump probability → Strong entry candidate"
            "\n"
            "- 50-69: 🟠 HIGH pump probability → Good entry with risk management"
            "\n"
            "- 30-49: 🟡 MODERATE → Wait for confirmation"
            "\n"
            "- <30: 🟢 LOW → Skip this stock"
            "\n\n"
            "**Final Output:**"
            "\n"
            "Provide a concise pump analysis with:"
            "\n"
            "- Pump Probability Score (0-100)"
            "\n"
            "- Key detected signals"
            "\n"
            "- Trading recommendation (BUY/WAIT/SKIP)"
            "\n"
            "- Risk level assessment"
        )
        
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant specialized in pump detection. "
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
            user_input = f"Analyze {ticker} for pump opportunities using all detection methods."
            state["messages"] = [("user", user_input)]
        
        # Invoke the chain
        result = chain.invoke(state)
        
        # Add pump analysis to state
        return {
            "messages": state["messages"] + [result],
            "pump_report": result.content if hasattr(result, 'content') else str(result),
        }
    
    return pump_detection_node
