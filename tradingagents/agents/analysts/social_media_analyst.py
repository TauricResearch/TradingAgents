from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_social_tools,
    build_instrument_context,
    has_social_sentiment_support,
)


def create_social_media_analyst(llm, social_sentiment_available: bool | None = None):
    def social_media_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        social_sentiment_enabled = social_sentiment_available
        if social_sentiment_enabled is None:
            social_sentiment_enabled = has_social_sentiment_support()

        tools = build_social_tools(social_sentiment_enabled)
        sentiment_guidance = ""
        if social_sentiment_enabled:
            sentiment_guidance = (
                " When available, use the get_social_sentiment(ticker, curr_date, look_back_days) tool first to capture current cross-source social sentiment from Reddit, X/Twitter, and Polymarket. If the social sentiment tool reports that the requested trade date is historical, rely on news context and state that live social sentiment was unavailable for that backtest date."
            )

        system_message = (
            "You are a social media and company specific news researcher/analyst tasked with analyzing social media posts, recent company news, and public sentiment for a specific company over the past week. You will be given a company's name and your objective is to write a comprehensive long report detailing your analysis, insights, and implications for traders and investors."
            + sentiment_guidance
            + " Then use the get_news(query, start_date, end_date) tool to add company-specific news context. Provide specific, actionable insights with supporting evidence to help traders make informed decisions."
            + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    " You have access to the following tools: {tool_names}.\n{system_message}"
                    "For your reference, the current date is {current_date}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

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
