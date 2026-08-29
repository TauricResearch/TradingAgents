"""
Derivatives Analyst agent.

Analyzes options, futures, and crypto derivatives for investment
and hedging opportunities.
"""

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    get_fundamentals,
    get_instrument_context_from_state,
    get_language_instruction,
)


def create_derivatives_analyst(llm):
    """Create the derivatives analyst node."""

    def derivatives_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = get_instrument_context_from_state(state)

        tools = [
            get_fundamentals,
        ]

        system_message = (
            "You are a derivatives analyst specializing in options, futures, and crypto derivatives. "
            "Your role is to analyze derivative instruments for both INVESTMENT and HEDGING purposes.\n\n"
            "For each analysis, provide:\n"
            "1. **Available Derivatives**: List relevant options (calls/puts), futures, or crypto derivatives\n"
            "2. **Pricing Analysis**: Current premiums, implied volatility, time decay\n"
            "3. **Risk Metrics**: Delta, Gamma, Theta, Vega (where applicable)\n"
            "4. **Strategy Recommendations**:\n"
            "   - Investment: Directional plays, spreads, straddles\n"
            "   - Hedging: Protective puts, covered calls, collar strategies\n"
            "5. **Cost-Benefit Analysis**: Premium costs vs protection/gains\n"
            "6. **Scoring**: Rate each strategy 0-100 based on risk/reward\n\n"
            "Always present predictions as SCENARIOS, not facts.\n"
            "Always include a Markdown table summarizing key derivatives metrics.\n"
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
                    " You have access to the following tools: {tool_names}."
                    " Today's date is {current_date}; treat it as 'now' for all analysis and tool-call date ranges. {instrument_context}\n"
                    "{system_message}",
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

    return derivatives_analyst_node
