from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    get_market_movers, 
    get_earnings_calendar,
    get_insider_transactions,
    get_indicators,
    get_trending_social
)

def create_screening_agent(llm):
    """
    Creates a screening agent that identifies potential stocks to analyze.
    """
    def screening_agent_node(state):
        # Tools available to the screening agent
        tools = [get_market_movers, get_earnings_calendar, get_insider_transactions, get_indicators, get_trending_social]
        
        system_message = (
            "You are a Market Screening Agent. Your goal is to identify 'Hidden Gem' stocks before they make a massive move."
            " Do NOT just recommend stocks that have already risen 50%+ (unless there is a fresh catalyst)."
            " Use a multi-factor approach:"
            " 1. **Scan**: Use `get_market_movers` to find 'Most Active' or 'Top Losers' (potential reversals). Avoid chasing 'Top Gainers' if they are already up significantly."
            " 2. **Social Hype**: Use `get_trending_social` to find stocks buzzing on Reddit/StockTwits. High chatter + low price movement = potential breakout."
            " 3. **Catalyst**: Use `get_earnings_calendar` to find upcoming earnings."
            " 4. **Smart Money**: Use `get_insider_transactions` on interesting tickers. If insiders are buying, it's a strong signal."
            " 5. **Technicals**: Use `get_indicators` (RSI, MACD) to check if a stock is Oversold (RSI < 30) or showing divergence."
            " \n"
            " **Strategy**: Look for stocks that are active but haven't spiked yet, or are beaten down (Losers) with insider buying."
            " Analyze the data and recommend 1-3 tickers."
            " Return your recommendations as a comma-separated list of tickers in the final response, e.g., 'NVDA, TSLA, AAPL'."
            " Do not include any other text in the final line, just the tickers."
        )
        
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant."
                    " You have access to the following tools: {tool_names}.\n{system_message}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )
        
        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        
        # Bind tools to the LLM
        chain = prompt | llm.bind_tools(tools)
        
        # Invoke the chain
        # For screening, we might not have a full conversation history yet, so we can start with a user request
        if not state.get("messages"):
             state["messages"] = [("user", "Please screen the market and find interesting stocks.")]

        result = chain.invoke(state["messages"])
        
        return {
            "messages": [result],
            # We could parse the result here and put it in a specific state key if needed
        }

    return screening_agent_node
