from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import get_instrument_context_from_state, get_language_instruction
from tradingagents.agents.utils.india_market_tools import (
    get_india_financial_results,
    get_india_fundamentals,
    get_india_sector_context,
    get_india_shareholding_pattern,
    get_local_filing_notes,
)


def create_india_fundamentals_analyst(llm):
    def india_fundamentals_node(state):
        current_date = state["trade_date"]
        instrument_context = get_instrument_context_from_state(state)
        tools = [
            get_india_fundamentals,
            get_india_financial_results,
            get_india_shareholding_pattern,
            get_india_sector_context,
            get_local_filing_notes,
        ]
        system_message = (
            "You are the India Fundamentals Analyst for IndiaMarketAgents. Focus on business quality, "
            "earnings quality, balance sheet quality, working capital, capex, ROCE/ROE if available, "
            "promoter/FII/DII/public shareholding, pledge risk, related-party or governance flags, "
            "and valuation context only when data exists. Apply India sector checklists with extra "
            "attention to pharma, chemicals, and oil & gas. Output business quality, earnings quality, "
            "balance sheet quality, valuation context, governance, sector lens, top 5 positives, "
            "top 5 concerns, and data gaps. Do not fabricate unavailable filings or shareholding. "
            "Use research-only language, not personal advice or order instructions, and include "
            "data-quality caveats for any yfinance or unavailable-source content."
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
        return {"messages": [result], "fundamentals_report": report, "india_fundamentals_report": report}

    return india_fundamentals_node
