from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
from tradingagents.agents.utils.agent_utils import get_news, get_global_news
from tradingagents.dataflows.config import get_config


def create_profile_analyst(llm):
    def profile_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["ticker_of_interest"]

        tools = [
            # get_news,
            # get_global_news,
        ]

        system_message = """You are a Profile and Portfolio Analyst tasked with providing a deep-dive assessment of the user's personal trading account and financial health. Your role is to bridge the gap between market opportunities and the user's actual capacity to trade. Your objective is to write a comprehensive report detailing the user's buying power, asset allocation, risk exposure, and active market participation.

                Use the available tools:
                - `get_account_balance`: To determine total equity, available free margin for new trades, and locked capital.
                - `get_portfolio_holdings`: To analyze current asset distribution, sector concentration (e.g., heavy on DeFi vs. Layer 1s), and unrealized PnL.
                - `get_open_orders`: To identify capital tied up in pending limit orders or stop-losses that may need adjustment.
                - `get_trade_history`: To review recent trading performance and identify behavioral patterns (e.g., panic selling or FOMO buying).

                Do not simply list the user's balances or holdings. You must provide detailed and finegrained analysis and insights. For instance, warn the user if they are overexposed to a single volatile asset, point out if they have too many "stale" open orders locking up funds that could be used elsewhere, or analyze if their current cash position allows for aggressive or conservative moves based on the market conditions. Your report should serve as a risk management check before any new trades are executed. Make sure to append a Markdown table at the end of the report to organize key portfolio metrics (Total Equity, Free Margin, Top Holdings, Risk Level) and actionable recommendations, organized and easy to read."""

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
            "news_report": report,
        }

    return profile_analyst_node
