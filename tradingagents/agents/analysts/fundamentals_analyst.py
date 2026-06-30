import logging

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_income_statement,
    get_instrument_context_from_state,
    get_language_instruction,
    get_strict_data_instruction,
    get_verified_market_snapshot,
    strip_think_tags,
)
from tradingagents.agents.utils.tool_call_recovery import (
    log_tool_call_failure,
    recover_tool_calls,
)

logger = logging.getLogger(__name__)


def create_fundamentals_analyst(llm):
    def fundamentals_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state.get("company_of_interest", "UNKNOWN")
        instrument_context = get_instrument_context_from_state(state)

        tools = [
            get_fundamentals,
            get_balance_sheet,
            get_cashflow,
            get_income_statement,
            get_verified_market_snapshot,
        ]

        system_message = (
            "You are a Fundamentals Analyst. Your goal is to provide a comprehensive "
            "fundamental analysis of the given company.\n\n"
            "STEP 1 — Call these tools in order:\n"
            f"  1. get_fundamentals(ticker, curr_date={current_date})\n"
            f"  2. get_income_statement(ticker, freq='quarterly', curr_date={current_date})\n"
            f"  3. get_balance_sheet(ticker, freq='quarterly', curr_date={current_date})\n"
            f"  4. get_cashflow(ticker, freq='quarterly', curr_date={current_date})\n"
            f"  5. get_verified_market_snapshot(symbol, curr_date={current_date})\n\n"
            "STEP 2 — Write a comprehensive report that MUST include ALL of the following sections:\n"
            "1. **Company Overview** — what the company does, sector, exchange\n"
            "2. **Key Valuation Metrics** — P/E, P/B, Market Cap (use CORRECT CURRENCY from the data)\n"
            "3. **Revenue & Profitability** — revenue trend, net income, margins\n"
            "4. **Balance Sheet Strength** — assets, liabilities, debt-to-equity\n"
            "5. **Cash Flow Quality** — operating and free cash flow\n"
            "6. **Growth Outlook** — analyst estimates if available\n"
            "7. **Key Risks** — debt, competition, regulatory, macro\n"
            "8. **Summary Table** — Markdown table: Metric | Value | Assessment\n\n"
            "CRITICAL RULES:\n"
            "- Use ONLY data returned by the tools. Do NOT fabricate ANY figures.\n"
            "- Use the correct currency symbol from the data (INR for ICICIBANK.NS, etc.).\n"
            "- Do NOT invent regulatory bodies, institutions, or organizations.\n"
            "- If a tool returns no data, write N/A for those fields."
            + "\nCRITICAL: Before writing the final report, call `get_verified_market_snapshot` "
            "for this ticker and treat it as the ground truth for Market Cap and Stock Price."
            + get_strict_data_instruction()
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

        result, recovered = recover_tool_calls(result, tools, logger)
        log_tool_call_failure("Fundamentals Analyst", ticker, [t.name for t in tools], result, logger)

        report = ""
        if len(result.tool_calls) == 0:
            report = strip_think_tags(result.content)

        return {
            "messages": [result] + recovered,
            "fundamentals_report": report,
        }

    return fundamentals_analyst_node
