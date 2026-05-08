from langchain_core.messages import HumanMessage, SystemMessage
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_global_news,
    get_language_instruction,
    get_news,
)
from tradingagents.agents.utils.tool_utils import dispatch_tool_calls


def create_news_analyst(llm):

    def news_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [get_news, get_global_news]
        llm_with_tools = llm.bind_tools(tools)
        tool_map = {t.name: t for t in tools}

        system_message = (
            "You are a news researcher tasked with analyzing recent news and trends over the past week. Please write a comprehensive report of the current state of the world that is relevant for trading and macroeconomics. Use the available tools: get_news(query, start_date, end_date) for company-specific or targeted news searches, and get_global_news(curr_date, look_back_days, limit) for broader macroeconomic news. Provide specific, actionable insights with supporting evidence to help traders make informed decisions."
            + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""
            + get_language_instruction()
        )

        messages = [
            SystemMessage(
                content=(
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    f" You have access to the following tools: {', '.join(tool_map)}.\n{system_message}"
                    f" For your reference, the current date is {current_date}. {instrument_context}"
                )
            ),
            HumanMessage(content=state["company_of_interest"]),
        ]

        while True:
            result = llm_with_tools.invoke(messages)
            messages.append(result)
            if not result.tool_calls:
                break
            messages.extend(dispatch_tool_calls(tool_map, result.tool_calls))

        return {"analyst_reports": {"news": result.content}}

    return news_analyst_node
