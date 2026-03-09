from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
from tradingagents.agents.utils.agent_utils import get_news, get_global_news
from tradingagents.dataflows.config import get_config


def get_news_analyst_system_message(language="en"):
    """Get news analyst system message in the specified language."""
    if language == "zh_TW":
        return "你是一位新聞研究員，負責分析過去一周的最近新聞和趨勢。請寫一份全面的報告，說明對於交易和宏觀經濟相關的當前世界狀況。使用可用工具：get_news(query, start_date, end_date) 用於公司特定或針對性的新聞搜索，以及 get_global_news(curr_date, look_back_days, limit) 用於更廣泛的宏觀經濟新聞。不要簡單地說趨勢是混合的，提供詳細的細緻分析和見解，以幫助交易員做出決策。" + """ 確保在報告末尾附加 Markdown 表格以組織關鍵點，清晰易讀。"""
    else:
        return "You are a news researcher tasked with analyzing recent news and trends over the past week. Please write a comprehensive report of the current state of the world that is relevant for trading and macroeconomics. Use the available tools: get_news(query, start_date, end_date) for company-specific or targeted news searches, and get_global_news(curr_date, look_back_days, limit) for broader macroeconomic news. Do not simply state the trends are mixed, provide detailed and finegrained analysis and insights that may help traders make decisions." + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""


def create_news_analyst(llm):
    def news_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        
        # Get language from config, default to English
        config = get_config()
        language = config.get("language", "en")

        tools = [
            get_news,
            get_global_news,
        ]

        system_message = get_news_analyst_system_message(language)

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
                    "For your reference, the current date is {current_date}. We are looking at the company {ticker}",
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

    return news_analyst_node
