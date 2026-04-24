from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import build_instrument_context, get_language_instruction, get_news
from tradingagents.dataflows.config import get_config


def create_social_media_analyst(llm):
    def social_media_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [
            get_news,
        ]

        system_message = (
            "你是一位社交媒体和公司特定新闻的研究员/分析师，负责分析过去一周特定公司的社交媒体帖子、近期公司新闻和公众情绪。你将获得一个公司的名称，你的目标是撰写一份详细的长篇报告，详细说明你对该公司当前状态的分析、洞察和对交易者和投资者的影响，方法是查看社交媒体和人们对这家公司的评价，分析人们每天对公司的情绪数据，以及查看近期公司新闻。使用get_news(query, start_date, end_date)工具搜索公司特定新闻和社交媒体讨论。尝试查看所有可能的来源，从社交媒体到情绪再到新闻。提供具体的、可操作的洞察和支持证据，以帮助交易者做出明智的决策。"
            + """ 请务必在报告末尾附加一个Markdown表格，以组织和便于阅读的方式呈现报告中的关键点。"""
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是一位乐于助人的AI助手，与其他助手协作。使用提供的工具来推进回答问题。"
                    " 如果你无法完全回答，没关系；另一位拥有不同工具的助手将帮助你完成未完成的部分。执行你能做的以取得进展。"
                    " 如果你或任何其他助手有最终的**交易提案：买入/持有/卖出**或交付物，"
                    " 请在你的回复前加上 **最终交易提案：买入/持有/卖出**，以便团队知道停止。"
                    " 你可以使用以下工具：{tool_names}。\n{system_message}"
                    "供参考，当前日期是{current_date}。{instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

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
