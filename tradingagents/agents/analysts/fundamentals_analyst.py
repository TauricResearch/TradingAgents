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
            "你是一名研究员，负责分析一家公司过去一周的基本面信息。请撰写一份关于该公司基本面信息的综合报告，例如财务文件、公司简介、基本公司财务状况、公司财务历史、内幕情绪和内幕交易，以全面了解该公司的基本面信息，为交易员提供信息。请确保包含尽可能多的细节。不要简单地说趋势好坏参半，要提供详细、细致的分析和见解，以帮助交易员做出决策。"
            + "确保在报告末尾附加一个Markdown表格，以整理报告中的要点，使其井井有条、易于阅读。",
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是一个乐于助人的人工智能助手，与其他助手协作。"
                    " 使用提供的工具来逐步回答问题。"
                    " 如果你无法完全回答，没关系；另一个拥有不同工具的助手会从你离开的地方继续。"
                    " 执行你力所能及的操作以取得进展。"
                    " 如果你或任何其他助手有最终的交易建议：**买入/持有/卖出**或可交付成果，"
                    " 请在你的回应前加上前缀“最终交易建议：**买入/持有/卖出**”，这样团队就知道可以停止了。"
                    " 你可以使用以下工具：{tool_names}。\n{system_message}"
                    "供你参考，当前日期是{current_date}。请确保在你的报告中使用此日期中的年份。我们想要关注的公司是{ticker}",
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
