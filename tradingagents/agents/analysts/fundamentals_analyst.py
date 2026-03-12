from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
from tradingagents.agents.utils.agent_utils import (
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement,
    get_insider_transactions,
    get_krx_fundamentals,
    get_dart_financials,
    get_dart_shareholders,
)
from tradingagents.agents.utils.korean_prompt import (
    KOREAN_INVESTOR_GUIDE,
    KOREAN_REPORT_FORMAT_GUIDE,
    SWING_TRADING_CONTEXT,
    SWING_PORTFOLIO_CONTEXT,
)
from tradingagents.dataflows.config import get_config


def create_fundamentals_analyst(llm):
    def fundamentals_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        company_name = state["company_of_interest"]

        config = get_config()
        market = config.get("market", "US") if config else "US"

        if market == "KRX":
            tools = [
                get_krx_fundamentals,
                get_dart_financials,
                get_dart_shareholders,
            ]
        else:
            tools = [
                get_fundamentals,
                get_balance_sheet,
                get_cashflow,
                get_income_statement,
            ]

        system_message = (
            "You are a researcher tasked with analyzing fundamental information over the past week about a company. Please write a comprehensive report of the company's fundamental information such as financial documents, company profile, basic company financials, and company financial history to gain a full view of the company's fundamental information to inform traders. Make sure to include as much detail as possible. Do not simply state the trends are mixed, provide detailed and finegrained analysis and insights that may help traders make decisions."
            + " Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."
            + " Use the available tools: `get_fundamentals` for comprehensive company analysis, `get_balance_sheet`, `get_cashflow`, and `get_income_statement` for specific financial statements."
            + KOREAN_INVESTOR_GUIDE
            + KOREAN_REPORT_FORMAT_GUIDE
            + SWING_TRADING_CONTEXT
            + SWING_PORTFOLIO_CONTEXT
        )

        # Inject swing context if available
        screening_ctx = state.get("screening_context", "")
        portfolio_ctx = state.get("portfolio_context", "")
        position_status = state.get("position_status", "NONE")
        if screening_ctx or portfolio_ctx:
            system_message += f"\n\n[현재 분석 컨텍스트]\n포지션 상태: {position_status}\n"
            if screening_ctx:
                system_message += f"스크리닝 선정 이유: {screening_ctx}\n"
            if portfolio_ctx:
                system_message += f"\n{portfolio_ctx}\n"

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/PASS** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/PASS** so the team knows to stop."
                    " You have access to the following tools: {tool_names}.\n{system_message}"
                    "For your reference, the current date is {current_date}. The company we want to look at is {ticker}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(ticker=ticker)

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
