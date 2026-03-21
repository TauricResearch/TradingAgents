from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
from tradingagents.agents.utils.fundamental_data_tools import (
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement,
    get_ttm_analysis,
    get_peer_comparison,
    get_sector_relative,
)
from tradingagents.agents.utils.news_data_tools import get_insider_transactions
from tradingagents.dataflows.config import get_config


def create_fundamentals_analyst(llm):
    def fundamentals_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        company_name = state["company_of_interest"]

        tools = [
            get_ttm_analysis,
            get_fundamentals,
            get_balance_sheet,
            get_cashflow,
            get_income_statement,
            get_peer_comparison,
            get_sector_relative,
        ]

        system_message = (
            "You are a researcher tasked with performing deep fundamental analysis of a company over the last 8 quarters (2 years) to support medium-term investment decisions."
            " Follow this sequence:"
            " 1. Call `get_ttm_analysis` first — this provides a Trailing Twelve Months (TTM) trend report covering revenue growth (QoQ and YoY), margin trajectories (gross, operating, net), return on equity trend, debt/equity trend, and free cash flow over 8 quarters."
            " 2. Call `get_fundamentals` for the latest snapshot of key ratios (PE, PEG, price-to-book, beta, 52-week range)."
            " 3. Call `get_peer_comparison` to see how the company ranks against sector peers over 1-week, 1-month, 3-month, and 6-month periods."
            " 4. Call `get_sector_relative` to compute the company's alpha vs its sector ETF benchmark."
            " 5. Optionally call `get_balance_sheet`, `get_cashflow`, or `get_income_statement` for additional detail."
            " Write a comprehensive report covering: multi-quarter revenue and margin trends, TTM metrics, relative valuation vs peers, sector outperformance or underperformance, and a clear medium-term fundamental thesis."
            " Do not simply state trends are mixed — provide detailed, fine-grained analysis that identifies inflection points, acceleration or deceleration in growth, and specific risks and opportunities."
            " Make sure to append a Markdown summary table at the end of the report organising key metrics for easy reference.",
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
