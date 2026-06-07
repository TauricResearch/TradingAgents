from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import get_instrument_context_from_state, get_language_instruction
from tradingagents.agents.utils.india_market_tools import (
    get_india_corporate_actions,
    get_india_corporate_announcements,
    get_india_financial_results,
    get_local_filing_notes,
)


def create_india_news_filings_analyst(llm):
    def india_news_filings_node(state):
        current_date = state["trade_date"]
        instrument_context = get_instrument_context_from_state(state)
        tools = [
            get_india_corporate_announcements,
            get_india_financial_results,
            get_india_corporate_actions,
            get_local_filing_notes,
        ]
        system_message = (
            "You are the India News & Filings Analyst. Prioritize NSE/BSE announcements, board "
            "meetings, financial results, investor presentations, corporate actions, management "
            "changes, order wins, regulatory notices, rating actions, plant/regulatory events, "
            "litigation, M&A, and policy sensitivity. Output an event timeline, materiality "
            "assessment, what changed, source table, and unknowns. If exchange data is unavailable, "
            "say so plainly and do not fill gaps from memory."
            + get_language_instruction()
        )
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a serious buy-side India-market research assistant. "
                    "Use the provided tools and report unavailable data explicitly. "
                    "Tools: {tool_names}.\n{system_message}\n"
                    "Current date: {current_date}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )
        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join(tool.name for tool in tools))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)
        result = (prompt | llm.bind_tools(tools)).invoke(state["messages"])
        report = "" if result.tool_calls else result.content
        return {"messages": [result], "news_report": report, "india_news_filings_report": report}

    return india_news_filings_node
