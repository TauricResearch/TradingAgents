import logging

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    get_instrument_context_from_state,
    get_language_instruction,
    get_strict_data_instruction,
    strip_think_tags,
)
from tradingagents.agents.utils.quant_data_tools import get_quantitative_metrics
from tradingagents.agents.utils.tool_call_recovery import (
    log_tool_call_failure,
    recover_tool_calls,
)

logger = logging.getLogger(__name__)


def create_quant_analyst(llm):
    def quant_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state.get("company_of_interest", "UNKNOWN")
        instrument_context = get_instrument_context_from_state(state)

        tools = [get_quantitative_metrics]

        system_message = (
            "You are a Quantitative Risk Analyst. Your job is to statistically evaluate the "
            "risk and return characteristics of the given instrument.\n\n"
            "STEP 1 — Call get_quantitative_metrics with:\n"
            "  ticker = the ticker symbol\n"
            f"  curr_date = {current_date}   ← use this EXACT date\n\n"
            "STEP 2 — Write a detailed report that MUST include ALL of the following sections:\n"
            "1. **Volatility Profile** — annualized vol, is it high or low vs. market?\n"
            "2. **Risk Metrics** — VaR (95%), Expected Shortfall interpretation\n"
            "3. **Return Analysis** — Sharpe Ratio, annualized return quality\n"
            "4. **Distribution Analysis** — skewness and kurtosis implications for tail risk\n"
            "5. **Max Drawdown** — worst peak-to-trough loss and recovery context\n"
            "6. **Stop Loss Recommendation** — specific % or price level based on VaR/vol\n"
            "7. **Position Sizing Guidance** — how much of a portfolio to risk given stats\n"
            "8. **Summary Table** — Markdown table: Metric | Value | Interpretation"
            + get_strict_data_instruction()
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages([
            ("system",
             "You are a helpful AI assistant, collaborating with other assistants."
             " Use the provided tools to progress towards answering the question."
             " You have access to the following tools: {tool_names}."
             " Today's date is {current_date}; use this exact date in all tool calls. {instrument_context}\n"
             "{system_message}"),
            MessagesPlaceholder(variable_name="messages"),
        ])

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        chain = prompt | llm.bind_tools(tools)
        result = chain.invoke(state["messages"])

        result, recovered = recover_tool_calls(result, tools, logger)
        log_tool_call_failure("Quant Analyst", ticker, [t.name for t in tools], result, logger)

        report = ""
        if len(result.tool_calls) == 0:
            report = strip_think_tags(result.content)

        return {
            "messages": [result] + recovered,
            "quant_report": report,
        }

    return quant_analyst_node
