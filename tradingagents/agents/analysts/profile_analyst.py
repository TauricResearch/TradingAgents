from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
from tradingagents.agents.utils.agent_utils import get_account_balance, get_open_orders
from tradingagents.dataflows.config import get_config


def create_profile_analyst(llm):
    def profile_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["ticker_of_interest"]

        tools = [
            get_account_balance,
            get_open_orders,
        ]

        system_message = (
                            "You are a Profile and Portfolio Analyst tasked with providing a deep-dive assessment of the user's personal trading account and financial health. \
                            You will be given access to the user's portfolio data, your objective is to write a comprehensive long report detailing your analysis, insights, and implications for the user's trading capacity after assessing their buying power, asset allocation, risk exposure, and active market participation. \
                            Use the `get_account_balance(symbol)` tool (e.g., symbol='BTC/USDT') to determine total equity, free margin, and locked capital. Use the `get_open_orders(symbol)` tool (e.g., symbol='BTC/USDT') to identify capital tied up in pending limit orders or stop-losses. \
                            Do not simply list the user's balances or holdings, provide detailed and finegrained analysis and insights. For instance, warn the user if they are overexposed to a single volatile asset, point out if they have too many 'stale' open orders locking up funds, or analyze if their current cash position allows for aggressive moves. Your report should serve as a risk management check before any new trades are executed."
                            + """ Make sure to append a Markdown table at the end of the report to organize key portfolio metrics (Total Equity, Free Margin, Top Holdings, Risk Level) and actionable recommendations, organized and easy to read.""",
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
                    "For your reference, the current date is {current_date}. We are looking at the coin {ticker}",
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
            "profile_report": report,
        }

    return profile_analyst_node
