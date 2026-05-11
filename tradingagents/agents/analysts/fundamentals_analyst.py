from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_balance_sheet,
    get_cashflow,
    get_etf_holdings,
    get_etf_profile,
    get_fundamentals,
    get_income_statement,
    get_insider_transactions,
    get_language_instruction,
    is_etf_ticker,
)
from tradingagents.dataflows.config import get_config


def create_fundamentals_analyst(llm):
    def fundamentals_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        instrument_context = build_instrument_context(ticker)

        # Bind both toolsets; the system_message tells the LLM which to use.
        # Keeping the bound set fixed avoids per-call ToolNode reconfiguration.
        tools = [
            get_fundamentals,
            get_balance_sheet,
            get_cashflow,
            get_income_statement,
            get_etf_profile,
            get_etf_holdings,
        ]

        if is_etf_ticker(ticker):
            system_message = (
                "You are a researcher tasked with analyzing an ETF over the past week. ETFs are funds, not companies — write a comprehensive report covering the ETF's tracking strategy, top-holding concentration, sector / asset-class breakdown, AUM, expense ratio, and any premium / discount to NAV. Provide specific, actionable insights with supporting evidence to help traders make informed decisions."
                + " Make sure to append a Markdown table at the end of the report to organize key points, organized and easy to read."
                + " Use the available tools: `get_etf_profile` for the ETF's profile and sector weightings, and `get_etf_holdings` for the top constituents. The company-financial tools (`get_fundamentals`, `get_balance_sheet`, `get_cashflow`, `get_income_statement`) will return ETF-not-applicable placeholders — do not rely on them for ETF tickers."
                + get_language_instruction(),
            )
        else:
            system_message = (
                "You are a researcher tasked with analyzing fundamental information over the past week about a company. Please write a comprehensive report of the company's fundamental information such as financial documents, company profile, basic company financials, and company financial history to gain a full view of the company's fundamental information to inform traders. Make sure to include as much detail as possible. Provide specific, actionable insights with supporting evidence to help traders make informed decisions."
                + " Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."
                + " Use the available tools: `get_fundamentals` for comprehensive company analysis, `get_balance_sheet`, `get_cashflow`, and `get_income_statement` for specific financial statements."
                + get_language_instruction(),
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
