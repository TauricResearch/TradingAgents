from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_company_news,
    get_language_instruction,
    get_social_sentiment,
)


def create_social_media_analyst(llm):
    def social_media_analyst_node(state):
        current_date = state.get("analysis_date") or state["trade_date"]
        instrument_context = build_instrument_context(
            state["company_of_interest"],
            state.get("instrument_profile"),
        )

        tools = [
            get_social_sentiment,
            get_company_news,
        ]

        system_message = (
            "You are a company sentiment analyst. "
            "Your job is to assess public narrative, sentiment, and crowd positioning around the company without claiming direct social-media coverage unless a tool explicitly provides it. "
            "Use `get_social_sentiment(symbol, start_date, end_date)` for dedicated or clearly labeled news-derived sentiment context, and `get_company_news(symbol, start_date, end_date)` for direct company-news evidence. "
            "If the sentiment tool says a dedicated social provider is unavailable, explicitly state that you are working from news-derived sentiment instead of pretending you saw social posts. "
            "Write a detailed report covering sentiment drivers, tone shifts, narrative concentration, what is improving, what is deteriorating, and the main trading implications."
            " End with a Markdown table that summarizes key signals, evidence, and confidence."
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " Return the completed sentiment report directly once you have enough evidence."
                    " You have access to the following tools: {tool_names}.\n{system_message}"
                    " For your reference, the current date is {current_date}. {instrument_context}",
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
