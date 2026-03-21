from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.polymarket_tools import get_event_details, get_market_stats, get_leaderboard_signals


def create_event_analyst(llm):
    def event_analyst_node(state):
        current_date = state["trade_date"]
        event_id = state["event_id"]
        event_question = state["event_question"]

        tools = [get_event_details, get_market_stats, get_leaderboard_signals]

        system_message = (
            "You are a prediction market event analyst. Analyze the event's resolution criteria, deadline, base probability estimation, and top trader signals. "
            "Focus on: resolution conditions and how likely they are to be met, time remaining until resolution, historical patterns from similar events, and what top traders are doing. "
            "Use get_event_details to retrieve the event description and resolution criteria. Use get_market_stats to get open interest and trading statistics. Use get_leaderboard_signals to understand what top traders are positioning. "
            "Write a detailed analytical report with specific observations. Do not simply say outcomes are uncertain — provide reasoned probability assessments based on the resolution criteria and market data. "
            "Append a Markdown table summarizing key findings at the end."
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

        return {"messages": [result], "event_report": report}

    return event_analyst_node
