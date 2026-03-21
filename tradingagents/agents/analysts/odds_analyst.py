from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.polymarket_tools import get_market_data, get_price_history, get_orderbook


def create_odds_analyst(llm):
    def odds_analyst_node(state):
        current_date = state["trade_date"]
        event_id = state["event_id"]
        event_question = state["event_question"]

        tools = [get_market_data, get_price_history, get_orderbook]

        system_message = (
            "You are a prediction market odds analyst. Your role is to analyze the current market odds, price history, and orderbook depth for a Polymarket event. "
            "Focus on: price trends and momentum, orderbook asymmetry (bid vs ask depth), volume patterns and liquidity, spread analysis, and smart money flow indicators. "
            "Use get_market_data to fetch current event prices and metadata. Use get_price_history with the token_id from market data to analyze price trends. Use get_orderbook to examine bid/ask depth. "
            "Write a detailed analytical report with specific numbers and trends. Do not simply say trends are mixed — provide actionable insights about whether the current market price fairly reflects the probability. "
            "Append a Markdown table summarizing key metrics at the end."
        )

        prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                "You are a helpful AI assistant, collaborating with other assistants. "
                "Use the provided tools to progress towards answering the question. "
                "Execute what you can to make progress. "
                "You have access to the following tools: {tool_names}.\n{system_message}"
                "The current date is {current_date}. The event we are analyzing: {event_question} (Event ID: {event_id})",
            ),
            MessagesPlaceholder(variable_name="messages"),
        ])

        prompt = prompt.partial(
            system_message=system_message,
            tool_names=", ".join([tool.name for tool in tools]),
            current_date=current_date,
            event_id=event_id,
            event_question=event_question,
        )

        chain = prompt | llm.bind_tools(tools)
        result = chain.invoke(state["messages"])

        report = ""
        if len(result.tool_calls) == 0:
            report = result.content

        return {"messages": [result], "odds_report": report}

    return odds_analyst_node
