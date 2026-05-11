"""Fundamentals analyst node.

The analytical framework is pluggable: the runtime config key
``fundamentals_style`` selects a registered style (see
``tradingagents.agents.analysts.fundamentals_styles``). The style
contributes both the system-prompt body and any extra tools beyond
the four default fundamental-data tools. Falls back to the default
style when the config value is missing or unknown so a typo can't
crash a run.
"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.analysts.fundamentals_styles import resolve_style
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_income_statement,
    get_language_instruction,
)
from tradingagents.runtime import get_runtime_config


# Tools every fundamentals style gets unconditionally. Styles can add more
# via their `extra_tools()` method but cannot subtract from this set —
# the four core financial statements are the irreducible inputs.
_BASE_TOOLS = [
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement,
]


def create_fundamentals_analyst(llm):
    def fundamentals_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        # Resolve style from runtime config; missing or unknown keys fall
        # back to the comprehensive default rather than raising.
        style = resolve_style(get_runtime_config().get("fundamentals_style"))
        tools = list(_BASE_TOOLS) + list(style.extra_tools())

        system_message = (
            style.system_message()
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
            "fundamentals_report": report,
        }

    return fundamentals_analyst_node
