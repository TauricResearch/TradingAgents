from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_income_statement,
    get_insider_transactions,
    get_language_instruction,
    get_local_file_info,
)
from tradingagents.dataflows.config import get_config


def create_fundamentals_analyst(llm):
    def fundamentals_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [
            get_fundamentals,
            get_balance_sheet,
            get_cashflow,
            get_income_statement,
            get_local_file_info,
        ]

        system_message = (
            "你是一位研究员，负责分析过去一周关于公司的基本面信息。请撰写一份综合报告，涵盖公司的基本面信息，如财务文档、公司简介、基本公司财务状况和公司财务历史，以全面了解公司的基本面信息，为交易者提供参考。请确保包含尽可能多的细节。提供具体的、可操作的洞察和支持证据，以帮助交易者做出明智的决策。"
            + " 请务必在报告末尾附加一个Markdown表格，以组织和便于阅读的方式呈现报告中的关键点。"
            + " 使用可用工具：`get_fundamentals`用于公司综合分析，`get_balance_sheet`用于资产负债表，`get_cashflow`用于现金流量表，`get_income_statement`用于利润表。"
            + " 此外，请务必调用 `get_local_file_info` 工具查询本地文件夹中是否有与该公司相关的文件（如交流纪要、内部研报等）。如果找到相关文件，请将其中的关键信息（管理层指引、业务进展、财务数据等）整合进你的基本面报告中，并明确标注来源为本地文件。"
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
            "fundamentals_report": report,
        }

    return fundamentals_analyst_node
