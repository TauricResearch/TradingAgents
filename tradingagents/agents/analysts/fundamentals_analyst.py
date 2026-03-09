from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
from tradingagents.agents.utils.agent_utils import get_fundamentals, get_balance_sheet, get_cashflow, get_income_statement, get_insider_transactions
from tradingagents.dataflows.config import get_config


def get_fundamentals_analyst_system_message(language="en"):
    """Get fundamentals analyst system message in the specified language."""
    if language == "zh_TW":
        return "你是一位研究員，負責分析公司過去一周的基本面信息。請寫一份全面的報告，深入分析公司的基本面信息，如財務文件、公司概況、基本財務狀況和公司財務歷史，以全面了解公司的基本面，為交易員提供參考。確保儘可能詳細。不要簡單地說趨勢是混合的，提供詳細的細緻分析和見解，以幫助交易員做出決策。" + " 確保在報告末尾附加 Markdown 表格以組織關鍵點，清晰易讀。" + " 使用可用工具：`get_fundamentals` 進行全面公司分析，`get_balance_sheet`, `get_cashflow` 和 `get_income_statement` 用於特定的財務報表。"
    else:
        return "You are a researcher tasked with analyzing fundamental information over the past week about a company. Please write a comprehensive report of the company's fundamental information such as financial documents, company profile, basic company financials, and company financial history to gain a full view of the company's fundamental information to inform traders. Make sure to include as much detail as possible. Do not simply state the trends are mixed, provide detailed and finegrained analysis and insights that may help traders make decisions." + " Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read." + " Use the available tools: `get_fundamentals` for comprehensive company analysis, `get_balance_sheet`, `get_cashflow`, and `get_income_statement` for specific financial statements."


def create_fundamentals_analyst(llm):
    def fundamentals_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        company_name = state["company_of_interest"]
        
        # Get language from config, default to English
        config = get_config()
        language = config.get("language", "en")

        tools = [
            get_fundamentals,
            get_balance_sheet,
            get_cashflow,
            get_income_statement,
        ]

        system_message = get_fundamentals_analyst_system_message(language)

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
