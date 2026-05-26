"""
Agent 全局状态定义（Agent State Schema）

在项目中的角色：
  - 这是 LangGraph 编排的多 Agent 交易系统的「共享内存」类型声明
  - 所有节点函数 (node) 的输入和输出都基于此 state 字典
  - 相当于整个系统的「数据契约」—— 哪些字段存在、各字段的语义是什么

三个状态类的层次关系：
  ┌─────────────────────────────────────────┐
  │  MessagesState（LangGraph 内置基类）      │
  │    ├── messages: 对话消息列表             │
  └──────────────┬──────────────────────────┘
                 │ 继承
  ┌──────────────▼──────────────────────────┐
  │  AgentState（主状态，本文件核心）          │
  │    ├── 输入参数：company, date, asset...  │
  │    ├── 分析报告：market, sentiment, news..│
  │    ├── 辩论子状态：InvestDebateState      │
  │    │           RiskDebateState            │
  │    └── 决策输出：plan, decision, context  │
  └─────────────────────────────────────────┘

关键设计：
  - 使用 Annotated[str, description] 为每个字段附加人类可读的描述
  - 这些描述会被 LangGraph Dev / 可视化工具用来生成状态文档
  - InvestDebateState 和 RiskDebateState 是嵌套的子状态，
    分别对应「投资辩论团队」和「风险管理团队」的内部对话状态
"""

from typing import Annotated
from typing_extensions import TypedDict
from langgraph.graph import MessagesState


# Researcher team state
class InvestDebateState(TypedDict):
    """投资辩论团队的内部状态。

    用于 Bull（看多）vs Bear（看空）两方分析师之间的多轮辩论。
    每次辩论轮次后，双方的历史发言被追加到对应字段，judge 根据完整历史做出裁决。

    典型生命周期：
        初始 → bull_history="" bear_history="" count=0
         ↓   （第1轮：Bull 发言）
        bull_history="..." count=1
         ↓   （第2轮：Bear 回应）
        bear_history="..." count=2
         ↓   ... 循环直到 judge_decision 产出
    """
    bull_history: Annotated[
        str, "Bullish Conversation history"
    ]  # Bullish Conversation history
    bear_history: Annotated[
        str, "Bearish Conversation history"
    ]  # Bullish Conversation history
    history: Annotated[str, "Conversation history"]  # Conversation history
    current_response: Annotated[str, "Latest response"]  # Last response
    judge_decision: Annotated[str, "Final judge decision"]  # Last response
    count: Annotated[int, "Length of the current conversation"]  # Conversation length


# Risk management team state
class RiskDebateState(TypedDict):
    """风险管理辩论团队的内部状态。

    用于三方（激进 / 保守 / 中立）风险分析师之间的多轮辩论。
    比 InvestDebateState 更复杂 —— 三方轮流发言，judge 综合三方观点给出最终风险评估。

    典型生命周期：
        初始 → 三方 history="" count=0
         ↓   （第1轮：Aggressive 发言）
        aggressive_history="..." current_aggressive_response="..." count=1
         ↓   （第2轮：Conservative 回应）
        conservative_history="..." count=2
         ↓   （第3轮：Neutral 评议）
        neutral_history="..." count=3
         ↓   ... 循环直到 judge_decision 产出
    """
    aggressive_history: Annotated[
        str, "Aggressive Agent's Conversation history"
    ]  # Conversation history
    conservative_history: Annotated[
        str, "Conservative Agent's Conversation history"
    ]  # Conversation history
    neutral_history: Annotated[
        str, "Neutral Agent's Conversation history"
    ]  # Conversation history
    history: Annotated[str, "Conversation history"]  # Conversation history
    latest_speaker: Annotated[str, "Analyst that spoke last"]
    current_aggressive_response: Annotated[
        str, "Latest response by the aggressive analyst"
    ]  # Last response
    current_conservative_response: Annotated[
        str, "Latest response by the conservative analyst"
    ]  # Last response
    current_neutral_response: Annotated[
        str, "Latest response by the neutral analyst"
    ]  # Last response
    judge_decision: Annotated[str, "Judge's decision"]
    count: Annotated[int, "Length of the current conversation"]  # Conversation length


class AgentState(MessagesState):
    """交易 Agent 系统的主状态类型 —— 所有节点共享的全局状态字典。

    继承自 LangGraph 的 MessagesState，自带 messages 字段（对话消息列表）。
    本类在此基础上扩展了完整的交易决策流水线所需的所有字段。

    字段按流水线阶段分组（见下方注释），反映了整个系统的执行时序：
        输入 → 研究(4路并行) → 投资辩论 → 交易计划 → 风险辩论 → 最终决策

    注意：
        - 每个字段都是 Annotated[T, description]，description 用于调试和可视化
        - 节点函数返回的 dict 只需包含要更新的字段，LangGraph 会自动 merge
        - 嵌套的 InvestDebateState / RiskDebateState 作为整体被各团队节点读写
    """

    # ═══════════════════════════════════════
    # 第1阶段：输入参数（系统启动时由用户/调度器填入）
    # ═══════════════════════════════════════
    company_of_interest: Annotated[str, "Company that we are interested in trading"]
    asset_type: Annotated[str, "Asset type under analysis such as stock or crypto"]
    trade_date: Annotated[str, "What date we are trading at"]

    sender: Annotated[str, "Agent that sent this message"]

    # ═══════════════════════════════════════
    # 第2阶段：研究报告（4个分析师节点并行产出）
    # ═══════════════════════════════════════
    market_report: Annotated[str, "Report from the Market Analyst"]
    sentiment_report: Annotated[str, "Report from the Sentiment Analyst"]
    news_report: Annotated[
        str, "Report from the News Researcher of current world affairs"
    ]
    fundamentals_report: Annotated[str, "Report from the Fundamentals Researcher"]

    # ═══════════════════════════════════════
    # 第3阶段：投资辩论（Bull vs Bear 多轮辩论后产出）
    # ═══════════════════════════════════════
    investment_debate_state: Annotated[
        InvestDebateState, "Current state of the debate on if to invest or not"
    ]
    investment_plan: Annotated[str, "Plan generated by the Analyst"]

    trader_investment_plan: Annotated[str, "Plan generated by the Trader"]

    # ═══════════════════════════════════════
    # 第4阶段：风险管理辩论（Aggressive vs Conservative vs Neutral 三方博弈）
    # ═══════════════════════════════════════
    risk_debate_state: Annotated[
        RiskDebateState, "Current state of the debate on evaluating risk"
    ]
    final_trade_decision: Annotated[str, "Final decision made by the Risk Analysts"]

    # ═══════════════════════════════════════
    # 跨轮次记忆：注入历史决策上下文，避免重复犯错
    # ═══════════════════════════════════════
    past_context: Annotated[str, "Memory log context injected at run start (same-ticker decisions + cross-ticker lessons)"]
