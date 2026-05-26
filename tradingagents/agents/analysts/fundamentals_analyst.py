"""
基本面分析师节点（Fundamentals Analyst Node）

在项目中的角色：
  - 属于 multi-agent 交易系统的「分析层」
  - 在 LangGraph 编排的有向图中作为一个独立节点运行
  - 职责：接收公司标识，调用金融数据工具，让 LLM 生成基本面分析报告

数据流：
  上游（输入）：state["company_of_interest"] / state["trade_date"] / state["messages"]
  本节点处理：组装工具 + Prompt → 调用 LLM → 提取报告文本
  下游（输出）：state["messages"]（追加LLM回复）+ state["fundamentals_report"]（纯文本报告）

设计模式：
  - 工厂模式：create_fundamentals_analyst(llm) 返回符合 LangGraph node 签名的闭包函数
  - Tool-calling 模式：通过 llm.bind_tools(tools) 让 LLM 自主决定调用哪些金融数据接口
"""

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_income_statement,
    get_insider_transactions,
    get_language_instruction,
)
from tradingagents.dataflows.config import get_config


def create_fundamentals_analyst(llm):
    """基本面分析师节点工厂函数。

    采用「闭包工厂」模式：外层接收 LLM 实例（依赖注入），内层返回一个
    符合 LangGraph node 签名的纯函数 (state) -> dict。
    这样做的优点：
      - 同一个 LLM 可被多个节点复用，避免重复初始化
      - 节点函数无额外参数，LangGraph 编排时可以直接调用

    Args:
        llm: 已配置好的 LangChain ChatModel 实例（如 ChatOpenAI）

    Returns:
        fundamentals_analyst_node: LangGraph 节点函数，接收 state 字典，返回包含
        messages 和 fundamentals_report 的状态更新字典
    """
    def fundamentals_analyst_node(state):
        """LangGraph 节点函数：执行基本面分析并返回状态更新。

        从 state 中提取交易日期和公司标识，组装工具链和 Prompt，
        调用 LLM 生成分析报告，将结果写回 state 的两个 key。

        Args:
            state: LangGraph 全局状态字典，至少包含:
                - company_of_interest: 目标公司标识（ticker 或名称）
                - trade_date: 当前模拟交易日期
                - messages: 对话历史消息列表

        Returns:
            dict: 状态更新，包含:
                - messages: 追加本次 LLM 回复（AIMessage，可能带 tool_calls）
                - fundamentals_report: 纯文本报告内容（仅当 LLM 未调用工具时非空）
        """
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        # 注册本节点可用的金融数据工具 —— LLM 会根据分析需要自主选择调用哪些
        tools = [
            get_fundamentals,       # 综合基本面数据（公司概况、关键指标）
            get_balance_sheet,      # 资产负债表
            get_cashflow,           # 现金流量表
            get_income_statement,   # 利润表
        ]

        # System prompt 拼接：角色定义 + 输出格式要求 + 工具说明 + 多语言指令
        system_message = (
            "You are a researcher tasked with analyzing fundamental information over the past week about a company. Please write a comprehensive report of the company's fundamental information such as financial documents, company profile, basic company financials, and company financial history to gain a full view of the company's fundamental information to inform traders. Make sure to include as much detail as possible. Provide specific, actionable insights with supporting evidence to help traders make informed decisions."
            + " Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."
            + " Use the available tools: `get_fundamentals` for comprehensive company analysis, `get_balance_sheet`, `get_cashflow`, and `get_income_statement` for specific financial statements."
            + get_language_instruction(),
        )

        # 构建 LangChain Prompt 模板：system 消息 + 对话历史占位符
        # system 消息中通过 {变量} 预留了运行时注入点
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
                    "For your reference, the current date is {current_date}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        # 逐步 partial 填充模板变量 —— 将运行时数据绑定到 Prompt
        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        # 构建执行链：Prompt → LLM（绑定工具集）
        # bind_tools 让 LLM 在生成回复时可选择发起 tool_call，而非直接输出文本
        chain = prompt | llm.bind_tools(tools)

        # 执行链式调用，传入对话历史消息
        result = chain.invoke(state["messages"])

        # 提取纯文本报告：仅当 LLM 直接回复文本（未调用任何工具）时才提取 content
        # 如果 LLM 发起了 tool_calls，report 为空字符串，实际数据由后续工具执行节点填充
        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        # 返回状态更新：messages 追加到对话历史，fundamentals_report 供下游节点消费
        return {
            "messages": [result],
            "fundamentals_report": report,
        }

    return fundamentals_analyst_node
