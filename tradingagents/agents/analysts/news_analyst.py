from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_global_news,
    get_language_instruction,
    get_news,
    get_options_chain,
)
from tradingagents.dataflows.config import get_config


def create_news_analyst(llm):
    def news_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [
            get_news,
            get_global_news,
            get_options_chain,
        ]

        system_message = (
            "You are a news analyst. Use get_news for company-specific searches and get_global_news for macroeconomic coverage. "
            "Also call get_options_chain once and cross-check its unusual-activity rows and day-over-day OI deltas against the news you collected: "
            "large positioning shifts that precede or coincide with a specific headline are stronger signals than either source alone — "
            "flag such confirmations (and contradictions) explicitly in the report. "
            "Write a report on recent news relevant to trading. Append a Markdown summary table at the end."
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "Use the provided tools to gather data and write your report."
                    " If you cannot fully answer, that's OK — your report will be used by downstream agents."
                    " Tools: {tool_names}.\n{system_message}"
                    " Current date: {current_date}. Strict-cutoff: use only data and events dated on or before this current date; never use later information. {instrument_context}",
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
