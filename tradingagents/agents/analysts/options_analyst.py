import logging

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    get_instrument_context_from_state,
    get_language_instruction,
    get_strict_data_instruction,
    strip_think_tags,
)
from tradingagents.agents.utils.options_data_tools import get_options_chain_metrics
from tradingagents.agents.utils.tool_call_recovery import (
    log_tool_call_failure,
    recover_tool_calls,
)

logger = logging.getLogger(__name__)


def create_options_analyst(llm):
    def options_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state.get("company_of_interest", "UNKNOWN")
        instrument_context = get_instrument_context_from_state(state)

        tools = [get_options_chain_metrics]

        system_message = (
            "You are an Options & Derivatives Analyst. Your goal is to gauge market sentiment "
            "and expected volatility from the options market.\n\n"
            "STEP 1 — Call get_options_chain_metrics with:\n"
            "  ticker = the ticker symbol\n"
            "(Note: options data is live and does not require a date parameter)\n\n"
            "STEP 2 — Write a detailed report that MUST include ALL of the following sections:\n"
            "1. **Market Sentiment via Options** — interpret Put/Call Volume and OI ratios\n"
            "2. **Implied Volatility** — current IV level and skew (put IV vs call IV)\n"
            "3. **Directional Bias** — what the options market implies about direction\n"
            "4. **Expected Price Range** — approximate expected move based on IV\n"
            "5. **Key Risk Events** — upcoming expirations or notable concentrations\n"
            "6. **Summary Table** — Markdown table: Metric | Value | Signal\n\n"
            "If options data is unavailable for this ticker, write: "
            "[OPTIONS DATA UNAVAILABLE — This ticker may not have listed options]"
            + get_strict_data_instruction()
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages([
            ("system",
             "You are a helpful AI assistant, collaborating with other assistants."
             " Use the provided tools to progress towards answering the question."
             " You have access to the following tools: {tool_names}."
             " Today's date is {current_date}. {instrument_context}\n"
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
        log_tool_call_failure("Options Analyst", ticker, [t.name for t in tools], result, logger)

        report = ""
        if len(result.tool_calls) == 0:
            report = strip_think_tags(result.content)

        return {
            "messages": [result] + recovered,
            "options_report": report,
        }

    return options_analyst_node
