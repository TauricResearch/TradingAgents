from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_options_data,
    get_language_instruction,
)
from tradingagents.dataflows.config import get_config
from tradingagents.agents.analyst_registry import register_analyst


@register_analyst(
    key="options",
    agent_node="Options Analyst",
    clear_node="Msg Clear Options",
    tool_node="tools_options",
    report_key="options_report",
    tools=[get_options_data],
)
def create_options_analyst(llm):

    def options_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [
            get_options_data,
        ]

        system_message = (
            """You are a trading assistant tasked with analyzing the options market for a given instrument. Your role is to use the get_options_data tool to fetch the options chain data, including Put/Call ratios and implied volatility.
            Assess what the options market is pricing in. A high Put/Call ratio might indicate bearish sentiment or a hedging environment, while high implied volatility suggests expected large price movements.
            Write a detailed and nuanced report of the options market trends you observe. Provide specific, actionable insights on what the derivatives market is signaling about the instrument's future price action."""
            + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""
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
            "options_report": report,
        }

    return options_analyst_node
