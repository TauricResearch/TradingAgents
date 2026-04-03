import re

from langchain_core.messages import ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.quant_tools import get_quant_analysis
from tradingagents.agents.utils.agent_utils import build_instrument_context, get_language_instruction


def _looks_like_raw_tool_call(text: str) -> bool:
    """Return True if the LLM output a tool call as plain text instead of via the API."""
    stripped = re.sub(r"^```+\w*\s*", "", text.strip())
    return bool(re.search(r'"name"\s*:', stripped) and re.search(r'"arguments"\s*:', stripped))


def create_quant_analyst(llm):

    def quant_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        instrument_context = build_instrument_context(ticker)

        tools = [get_quant_analysis]

        system_message = (
            "You are a quantitative analyst. Use the get_quant_analysis tool to retrieve "
            "statistical metrics for the stock. Interpret the results thoroughly: "
            "assess risk (annualised volatility, semideviation, tail risk via skewness and kurtosis), "
            "evaluate the return distribution (Jarque-Bera normality test), "
            "analyse the market relationship (beta, alpha, R², rolling correlation with SPY), "
            "and identify any structural concerns (fat tails, high downside deviation). "
            "Provide a structured Markdown report with a clear summary table and actionable insights."
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
                    " For your reference, the current date is {current_date}. {instrument_context}",
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
            content = result.content if isinstance(result.content, str) else ""
            if _looks_like_raw_tool_call(content):
                # The model output the tool call as plain text instead of using the
                # function-calling API (common with weaker/local models). Call the
                # tool directly so the quant data is always populated.
                try:
                    raw_data = get_quant_analysis.invoke(
                        {"ticker": ticker, "analysis_date": current_date}
                    )
                except Exception as e:
                    raw_data = f"Quant analysis unavailable: {e}"
                # Feed the raw data back to the LLM so it can write the narrative report.
                tool_msg = ToolMessage(content=raw_data, tool_call_id="fallback")
                followup = chain.invoke(state["messages"] + [result, tool_msg])
                fc = followup.content if isinstance(followup.content, str) else ""
                report = fc if fc and not _looks_like_raw_tool_call(fc) else raw_data
                result = followup
            else:
                report = content

        return {
            "messages": [result],
            "quant_report": report,
        }

    return quant_analyst_node
