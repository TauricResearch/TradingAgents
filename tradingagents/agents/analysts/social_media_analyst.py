from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.polymarket_tools import get_social_sentiment, get_whale_activity


def create_social_media_analyst(llm):
    def social_media_analyst_node(state):
        current_date = state["trade_date"]
        event_id = state["event_id"]
        event_question = state["event_question"]

        tools = [
            get_social_sentiment,
            get_whale_activity,
        ]

        system_message = (
            "You are a social sentiment analyst for prediction markets. "
            "Analyze social media opinion and whale/top trader positions for the event. "
            "Use get_social_sentiment(query) to gather Twitter and Reddit discussions related to the prediction market event. "
            "Use get_whale_activity(market_id) to identify what large holders are doing with their positions. "
            "Write a comprehensive report on public sentiment and large trader behavior. "
            "Do not simply state the trends are mixed — provide detailed and fine-grained analysis and insights that may help traders make decisions."
            " Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " Execute what you can to make progress."
                    " You have access to the following tools: {tool_names}.\n{system_message}"
                    "For your reference, the current date is {current_date}. The event we are analyzing: {event_question} (Event ID: {event_id})",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(event_id=event_id)
        prompt = prompt.partial(event_question=event_question)

        chain = prompt | llm.bind_tools(tools)

        result = chain.invoke(state["messages"])

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "sentiment_report": report,
        }

    return social_media_analyst_node
