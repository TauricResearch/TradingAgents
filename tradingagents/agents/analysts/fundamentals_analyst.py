from langchain_core.messages import HumanMessage, SystemMessage
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_income_statement,
    get_language_instruction,
)
from tradingagents.agents.utils.tool_utils import dispatch_tool_calls


def create_fundamentals_analyst(llm):

    def fundamentals_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [get_fundamentals, get_balance_sheet, get_cashflow, get_income_statement]
        llm_with_tools = llm.bind_tools(tools)
        tool_map = {t.name: t for t in tools}

        system_message = (
            "You are a researcher tasked with analyzing fundamental information over the past week about a company. Please write a comprehensive report of the company's fundamental information such as financial documents, company profile, basic company financials, and company financial history to gain a full view of the company's fundamental information to inform traders. Make sure to include as much detail as possible. Provide specific, actionable insights with supporting evidence to help traders make informed decisions."
            + " Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."
            + " Use the available tools: `get_fundamentals` for comprehensive company analysis, `get_balance_sheet`, `get_cashflow`, and `get_income_statement` for specific financial statements."
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

        return {"analyst_reports": {"fundamentals": result.content}}

    return fundamentals_analyst_node
