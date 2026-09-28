"""
/**
 * @module: TradingAgents
 * @file: credit_fundamentals_analyst.py
 * @description: Credit fundamentals analyst agent (leverage, coverage, cash flow, recovery rate)
 * @author: AI Assistant
 * @created: 2026-09-28T10:35:23
 * @updated: 2026-09-28T10:35:23
 * @version: 1.0.0
 * @reviewer:
 * @ai_reviewer:
 * @reviewer_date:
 */
"""

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_income_statement,
    get_instrument_context_from_state,
    get_language_instruction,
)
from tradingagents.dataflows.credit.anbima import (
    get_yield_curve,
    get_credit_spreads,
)


def create_credit_fundamentals_analyst(llm):
    """Create a credit fundamentals analyst node.
    
    Analyzes creditworthiness using leverage ratios, interest coverage,
    cash flow adequacy, asset quality, and recovery rate estimation.
    """
    def credit_fundamentals_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = get_instrument_context_from_state(state)

        tools = [
            get_fundamentals,
            get_balance_sheet,
            get_cashflow,
            get_income_statement,
            get_yield_curve,
            get_credit_spreads,
        ]

        system_message = (
            "You are a credit analyst specializing in Brazilian corporate bonds (debêntures). "
            "Analyze the creditworthiness of the issuer using the following framework:\n\n"
            "1. **Leverage ratios:** Net Debt/EBITDA, Debt/Equity, Debt/Assets\n"
            "2. **Interest coverage:** EBITDA/Interest Expense, EBIT/Interest Expense\n"
            "3. **Cash flow adequacy:** FCF/Debt, Operating Cash Flow/Debt, FCF/Interest\n"
            "4. **Asset quality:** Tangible asset coverage, recovery rate estimation\n"
            "5. **Profitability context:** EBITDA margin, ROA, ROE (for debt service capacity)\n\n"
            "Focus on **downside protection** and **default risk**, not upside potential. "
            "Provide a credit assessment: Investment Grade (BBB- or higher) or "
            "Speculative Grade (BB+ or lower) or Default risk.\n\n"
            "Use the available tools: `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, "
            "`get_income_statement` for financial data; `get_yield_curve` and `get_credit_spreads` "
            "for market data."
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other analysts."
                    " Use the provided tools to analyze creditworthiness."
                    " If you are unable to fully answer, that's OK; another analyst with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " Report what your tools support; another agent decides the credit decision."
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
            "fundamentals_report": report,
        }

    return credit_fundamentals_analyst_node
