from collections.abc import Mapping
from typing import Any

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_income_statement,
    get_instrument_context_from_state,
    get_language_instruction,
)
from tradingagents.dataflows import config


def build_fundamentals_prompt(state: Mapping[str, Any], *, output_language: str) -> str:
    """Build the complete fundamentals analyst system message without I/O.

    ``get_language_instruction()`` remains available for legacy callers.
    """
    current_date = state["trade_date"]
    instrument_context = get_instrument_context_from_state(state)
    body = (
        "You are a researcher tasked with analyzing fundamental information over the past week about a company. Please write a comprehensive report of the company's fundamental information such as financial documents, company profile, basic company financials, and company financial history to gain a full view of the company's fundamental information to inform traders. Make sure to include as much detail as possible. Provide specific, actionable insights with supporting evidence to help traders make informed decisions."
        + " Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."
        + " Use the available tools: `get_fundamentals` for comprehensive company analysis, `get_balance_sheet`, `get_cashflow`, and `get_income_statement` for specific financial statements."
        + get_language_instruction(output_language),
    )
    return (
        "You are a helpful AI assistant, collaborating with other assistants."
        " Use the provided tools to progress towards answering the question."
        " If you are unable to fully answer, that's OK; another assistant with different tools"
        " will help where you left off. Execute what you can to make progress."
        " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
        " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
        " You have access to the following tools: get_fundamentals, get_balance_sheet, get_cashflow, get_income_statement."
        f" Today's date is {current_date}; treat it as 'now' for all analysis and tool-call date ranges. {instrument_context}\n"
        + str(body)
    )


def create_fundamentals_analyst(llm):
    def fundamentals_analyst_node(state):
        tools = [get_fundamentals, get_balance_sheet, get_cashflow, get_income_statement]
        language = config.get_config().get("output_language", "English")
        prompt = ChatPromptTemplate.from_messages(
            [("system", "{system_message}"), MessagesPlaceholder(variable_name="messages")]
        ).partial(system_message=build_fundamentals_prompt(state, output_language=language))
        chain = prompt | llm.bind_tools(tools)
        result = chain.invoke(state["messages"])
        report = ""
        if len(result.tool_calls) == 0:
            report = result.content
        return {"messages": [result], "fundamentals_report": report}

    return fundamentals_analyst_node
