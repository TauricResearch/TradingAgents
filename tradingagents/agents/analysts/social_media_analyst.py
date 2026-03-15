from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
from tradingagents.agents.utils.agent_utils import get_news
from tradingagents.dataflows.config import get_config


def get_social_media_analyst_system_message(language="en"):
    """Get social media analyst system message in the specified language."""
    if language == "zh_TW":
        return "你是一位社交媒體和公司特定新聞研究員/分析師，負責分析特定公司的社交媒體帖子、最近的公司新聞和公眾情緒。你的目標是寫一份全面的詳細報告，分析該公司過去一周的最新狀況，包括社交媒體上人們在說什麼、分析公眾對該公司的每日情緒、查看最近的公司新聞。使用 get_news(query, start_date, end_date) 工具搜索公司特定的新聞和社交媒體討論。盡力查看所有可能的來源，包括社交媒體、情緒分析和新聞。不要簡單地說趨勢是混合的，提供詳細的細緻分析和見解，以幫助交易員做出決策。" + """ 確保在報告末尾附加 Markdown 表格以組織關鍵點，清晰易讀。"""
    else:
        return "You are a social media and company specific news researcher/analyst tasked with analyzing social media posts, recent company news, and public sentiment for a specific company over the past week. You will be given a company's name your objective is to write a comprehensive long report detailing your analysis, insights, and implications for traders and investors on this company's current state after looking at social media and what people are saying about that company, analyzing sentiment data of what people feel each day about the company, and looking at recent company news. Use the get_news(query, start_date, end_date) tool to search for company-specific news and social media discussions. Try to look at all sources possible from social media to sentiment to news. Do not simply state the trends are mixed, provide detailed and finegrained analysis and insights that may help traders make decisions." + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""


def create_social_media_analyst(llm):
    def social_media_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        company_name = state["company_of_interest"]
        
        # Get language from config, default to English
        config = get_config()
        language = config.get("language", "en")

        tools = [
            get_news,
        ]

        system_message = get_social_media_analyst_system_message(language)

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
                    "For your reference, the current date is {current_date}. The current company we want to analyze is {ticker}",
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
            "sentiment_report": report,
        }

    return social_media_analyst_node
