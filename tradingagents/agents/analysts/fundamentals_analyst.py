from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
from tradingagents.agents.utils.agent_utils import get_fundamentals, get_balance_sheet, get_cashflow, get_income_statement, get_insider_sentiment, get_insider_transactions
from tradingagents.dataflows.config import get_config


def create_fundamentals_analyst(llm):
    def fundamentals_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        company_name = state["company_of_interest"]

        tools = [
            get_fundamentals,
            get_balance_sheet,
            get_cashflow,
            get_income_statement,
        ]

        system_message = (
            "You are a Tactical Fundamental Analyst focused on SHORT-TERM (1-2 weeks) price catalysts. "
            "Your goal is to analyze financial data to identify immediate triggers that will move the price in the next 10 trading days. "
            "Ignore long-term 'intrinsic value' if it will not be realized this week. "
            "Look for approaching earnings beats, guidance raises, or immediate liquidity risks. "
            "Do not simply state the financials are good; determine if they are good ENOUGH to move the stock NOW."
            + "\n\nDECISION LOGIC:"
            + "\n- LONG: Approaching earnings beat, guidance raise, or undervalued with a specific near-term catalyst."
            + "\n- SHORT: Deteriorating fundamentals, liquidity crisis, or extreme overvaluation with a negative trigger."
            + "\n- HOLD: Valuation is fair, or no immediate fundamental catalysts exist."
            + "\n\nMake sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."
            + " Use the available tools: `get_fundamentals` for comprehensive company analysis, `get_balance_sheet`, `get_cashflow`, and `get_income_statement` for specific financial statements."
            + "\n\nYOU MUST CONCLUDE YOUR REPORT WITH: 'SIGNAL: [LONG/SHORT/HOLD]'"
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **LONG/HOLD/SHORT** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **LONG/HOLD/SHORT** so the team knows to stop."
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
