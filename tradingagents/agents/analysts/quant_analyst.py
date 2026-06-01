from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_quant_data,
    get_language_instruction,
)
from tradingagents.agents.analyst_registry import register_analyst


@register_analyst(
    key="quant",
    agent_node="Quant Analyst",
    clear_node="Msg Clear Quant",
    tool_node="tools_quant",
    report_key="quant_report",
    tools=[get_quant_data],
)
def create_quant_analyst(llm):

    def quant_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [
            get_quant_data,
        ]

        system_message = (
            """You are a quantitative trading assistant. Your role is to use the get_quant_data tool to fetch statistical metrics like Beta, Sharpe Ratio, and Volatility for the requested instrument compared to the broader market (SPY).
            Evaluate the risk-adjusted return and volatility of the asset. Is it a high-beta stock? Does it provide adequate returns for its volatility (Sharpe ratio)?
            Write a detailed, statistically-driven quantitative report. Provide actionable insights into the instrument's risk profile."""
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
            "quant_report": report,
        }

    return quant_analyst_node
