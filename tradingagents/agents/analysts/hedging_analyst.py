"""
Hedging Analyst agent.

Recommends hedging strategies across multiple markets using
derivatives, bonds, and correlation-based protection.
"""

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    get_fundamentals,
    get_instrument_context_from_state,
    get_language_instruction,
)


def create_hedging_analyst(llm):
    """Create the hedging analyst node."""

    def hedging_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = get_instrument_context_from_state(state)

        tools = [
            get_fundamentals,
        ]

        system_message = (
            "You are a hedging specialist focused on portfolio protection and risk mitigation. "
            "Your role is to design and recommend hedging strategies across multiple markets.\n\n"
            "For each hedging recommendation, provide:\n"
            "1. **Risk Assessment**: What risks need hedging (market, currency, interest rate, etc.)\n"
            "2. **Hedging Instruments**:\n"
            "   - Options: Protective puts, collars, covered calls\n"
            "   - Futures: Short futures for directional hedging\n"
            "   - Cross-asset: Bonds, gold, inverse ETFs\n"
            "   - Crypto: Perpetual shorts, put options\n"
            "3. **Hedge Ratio**: How much of the position to hedge (25%, 50%, 75%, 100%)\n"
            "4. **Cost Analysis**: Premium costs, margin requirements, opportunity cost\n"
            "5. **Effectiveness**: Expected reduction in portfolio volatility\n"
            "6. **Scoring**: Rate each strategy 0-100 based on cost vs protection\n\n"
            "Consider correlations between assets for optimal hedging.\n"
            "Always present as SCENARIOS with probability-weighted outcomes.\n"
            "Always include a Markdown table summarizing hedging strategies.\n"
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
            "hedging_report": report,
        }

    return hedging_analyst_node
