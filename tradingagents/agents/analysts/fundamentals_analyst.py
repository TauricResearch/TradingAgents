from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_income_statement,
)
from tradingagents.dataflows.interface import route_to_vendor
from tradingagents.dataflows.macro_regime import classify_macro_regime, format_macro_report
from tradingagents.dataflows.peer_comparison import (
    get_peer_comparison_report,
    get_sector_relative_report,
)
from tradingagents.dataflows.ttm_analysis import compute_ttm_metrics, format_ttm_report
def create_fundamentals_analyst(llm):
    def fundamentals_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        income_csv = route_to_vendor(
            "get_income_statement",
            ticker,
            "quarterly",
            current_date,
        )
        balance_csv = route_to_vendor(
            "get_balance_sheet",
            ticker,
            "quarterly",
            current_date,
        )
        cashflow_csv = route_to_vendor(
            "get_cashflow",
            ticker,
            "quarterly",
            current_date,
        )
        ttm_report = format_ttm_report(
            compute_ttm_metrics(income_csv, balance_csv, cashflow_csv, n_quarters=8),
            ticker,
        )
        peer_report = get_peer_comparison_report(ticker, current_date)
        sector_report = get_sector_relative_report(ticker, current_date)
        macro_regime_report = format_macro_report(classify_macro_regime(current_date))
        upstream_macro_report = state.get("macro_report", "").strip()
        macro_report = macro_regime_report
        if upstream_macro_report:
            macro_report = (
                f"{upstream_macro_report}\n\n## Medium-Term Macro Regime Overlay\n\n"
                f"{macro_regime_report}"
            )

        tools = [
            get_fundamentals,
            get_balance_sheet,
            get_cashflow,
            get_income_statement,
        ]

        system_message = (
            "You are a researcher tasked with analyzing fundamental information over the past week about a company. Please write a comprehensive report of the company's fundamental information such as financial documents, company profile, basic company financials, and company financial history to gain a full view of the company's fundamental information to inform traders. Make sure to include as much detail as possible. Provide specific, actionable insights with supporting evidence to help traders make informed decisions."
            + " Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."
            + " Use the available tools: `get_fundamentals` for comprehensive company analysis, `get_balance_sheet`, `get_cashflow`, and `get_income_statement` for specific financial statements."
            + f"\n\nPrecomputed medium-term context for {ticker}:"
            + f"\n\n[TTM Analysis]\n{ttm_report}"
            + f"\n\n[Peer Comparison]\n{peer_report}"
            + f"\n\n[Sector Relative Performance]\n{sector_report}"
            + f"\n\n[Macro Regime]\n{macro_report}"
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
            "fundamentals_report": report,
        }

    return fundamentals_analyst_node
