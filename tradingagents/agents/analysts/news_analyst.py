from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_global_news,
    get_language_instruction,
    get_news,
    get_local_file_info,
)
from tradingagents.dataflows.config import get_config


def create_news_analyst(llm):
    def news_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [
            get_news,
            get_global_news,
            get_local_file_info,
        ]

        system_message = (
            "你是一位新闻研究员，负责分析过去一周的最新新闻和趋势。请撰写一份关于当前世界状态的综合报告，这些内容与交易和宏观经济相关。使用可用工具：get_news(query, start_date, end_date)用于公司特定或定向新闻搜索，get_global_news(curr_date, look_back_days, limit)用于更广泛的宏观经济新闻。提供具体的、可操作的洞察和支持证据，以帮助交易者做出明智的决策。"
            + " 此外，请调用 `get_local_file_info` 工具查询本地文件夹中是否有与该公司相关的文件（如交流纪要、路演纪要等）。如果找到相关文件，请将其中涉及公司战略、管理层表态、市场动态的信息整合进你的新闻报告，作为一手信息源加以引用。"
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
            "news_report": report,
        }

    return news_analyst_node
