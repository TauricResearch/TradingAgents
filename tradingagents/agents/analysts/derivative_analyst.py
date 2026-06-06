from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
)
from tradingagents.agents.utils.prompt_cache import stable_join_sections
from tradingagents.agents.utils.derivatives_tools import (
    get_options_chain,
    get_options_overview,
)
from tradingagents.personas.prompt_overlay import apply_fragment


DERIVATIVES_SYSTEM_MESSAGE = (
    "You are a derivatives analyst. Analyze the options market for the instrument and "
    "explain what it implies for the underlying. Start with get_options_overview to frame "
    "expirations, implied volatility, and the put/call open-interest ratio, then pull "
    "get_options_chain for the nearest and one further expiry to inspect skew, liquidity, "
    "and notable strikes. Cover: (1) implied volatility level and term structure, "
    "(2) skew between put and call IV and what it says about hedging or positioning, "
    "(3) unusual volume or open-interest concentrations, "
    "(4) one or two concrete derivatives strategies an investor could consider with the "
    "directional thesis each expresses, and (5) the key risks: assignment, theta, and "
    "IV crush around events. Be specific and actionable; do not give generic options education. "
    "Append a Markdown table at the end summarizing key levels, IV, and strategies."
)


def build_derivatives_user_prompt(*, current_date: str, instrument_context: str) -> str:
    return stable_join_sections(
        [
            ("Trade Date", current_date),
            ("Instrument Context", instrument_context),
            (
                "Current Task",
                "Use the available derivatives tools to produce the options-market report.",
            ),
        ]
    )


def create_derivative_analyst(llm, persona=None):

    def derivative_analyst_node(state):
        current_date = state["trade_date"]
        asset_type = state.get("asset_type", "stock")
        instrument_context = build_instrument_context(
            state["company_of_interest"], asset_type
        )

        tools = [get_options_overview, get_options_chain]

        system_message = apply_fragment(
            DERIVATIVES_SYSTEM_MESSAGE + get_language_instruction(),
            persona,
        )
        user_prompt = build_derivatives_user_prompt(
            current_date=current_date,
            instrument_context=instrument_context,
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
                    " You have access to the following tools: {tool_names}.\n{system_message}",
                ),
                ("human", "{user_prompt}"),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(user_prompt=user_prompt)

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
