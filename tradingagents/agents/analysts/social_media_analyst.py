from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
from tradingagents.agents.utils.agent_utils import get_news
from tradingagents.dataflows.config import get_config


def create_social_media_analyst(llm):
    def social_media_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        company_name = state["company_of_interest"]

        tools = [
            get_news,
        ]

        system_message = (
            "你是一名社交媒体和公司特定新闻研究员/分析师，负责分析过去一周特定公司的社交媒体帖子、近期公司新闻和公众情绪。你将获得公司名称，你的目标是撰写一份全面的长篇报告，详细说明你的分析、见解以及对交易员和投资者关于该公司当前状况的影响，这需要查看社交媒体、人们对该公司的评价、分析人们每天对公司的情绪数据以及近期公司新闻。尽量查看所有可能的来源，从社交媒体到情绪数据再到新闻。不要简单地陈述趋势好坏参半，提供详细和精细的分析和见解，以帮助交易员做出决策。"
            + """确保在报告末尾附加一个Markdown表格，以整理报告中的要点，使其井井有条、易于阅读。""",
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
