from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
)
from tradingagents.agents.utils.derivatives_tools import (
    get_options_chain,
    get_options_overview,
)


def create_derivative_analyst(llm):

    def derivative_analyst_node(state):
        current_date = state["trade_date"]
        asset_type = state.get("asset_type", "stock")
        instrument_context = build_instrument_context(
            state["company_of_interest"], asset_type
        )

        tools = [get_options_overview, get_options_chain]

        system_message = (
            "You are a derivatives analyst. Analyze the options market for the instrument and "
            "explain what it implies for the underlying. Start with get_options_overview to frame "
            "expirations, implied volatility, and the put/call open-interest ratio, then pull "
            "get_options_chain for the nearest (and one further) expiry to inspect skew, liquidity, "
            "and notable strikes. Cover: (1) implied volatility level and term structure, "
            "(2) skew (put vs call IV) and what it says about hedging/positioning, "
            "(3) unusual volume or open-interest concentrations, "
            "(4) one or two concrete derivatives strategies an investor could consider "
            "(e.g. covered call, protective put, vertical spread) with the directional thesis each "
            "expresses, and (5) the key risks (assignment, theta, IV crush around events). "
            "Be specific and actionable; do not give generic options education."
            " Make sure to append a Markdown table at the end summarizing key levels, IV, and the "
            "strategies you discuss."
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
            "derivatives_report": report,
        }

    return derivative_analyst_node
