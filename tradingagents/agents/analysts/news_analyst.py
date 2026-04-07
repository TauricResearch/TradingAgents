from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_company_news,
    get_disclosures,
    get_language_instruction,
    get_macro_news,
)


def create_news_analyst(llm):
    def news_analyst_node(state):
        current_date = state.get("analysis_date") or state["trade_date"]
        instrument_context = build_instrument_context(
            state["company_of_interest"],
            state.get("instrument_profile"),
        )

        tools = [
            get_company_news,
            get_macro_news,
            get_disclosures,
        ]

        system_message = (
            "You are a news and event analyst. "
            "Build the report from three evidence blocks: company news, macro news, and disclosures. "
            "Use `get_company_news(symbol, start_date, end_date)` for company-specific coverage, "
            "`get_macro_news(curr_date, look_back_days, limit, region, language)` for broader market context, "
            "and `get_disclosures(symbol, start_date, end_date)` for filing or disclosure events when available. "
            "Do not describe unsupported tool signatures or imaginary search capabilities. "
            "Present 3 to 5 key events with event type, source, why it matters, bullish implication, bearish implication, and confidence. "
            "Finish with a concise Markdown table summarizing the evidence."
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
                    " Return the completed news report directly once you have enough evidence."
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
            "news_report": report,
        }

    return news_analyst_node
