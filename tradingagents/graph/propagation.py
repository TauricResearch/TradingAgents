"""
状态初始化与传播（State Initialization & Propagation）

在项目中的角色：
  - 负责 LangGraph 工作流执行前的「准备工作」：
    1. 构建完整的初始状态字典（AgentState 的所有字段）
    2. 配置图执行的运行参数（递归上限、回调等）
  - 是 trading_graph.py 中 _run_graph() 的直接调用者

为什么需要单独的类而不是在 trading_graph.py 中内联？
  - 职责分离：trading_graph 关注「编排流程」，propagator 关注「状态构建」
  - 可测试性：可以独立验证初始状态的正确性，无需启动完整图
  - 复用性：不同入口（CLI / API / 回测）都可以用同一个 Propagator

数据流：
  输入：company_name + trade_date + asset_type + past_context（来自 memory_log）
    ↓ create_initial_state()
  输出：完整的 AgentState 字典（所有字段初始化为空/零值）
    ↓ get_graph_args()
  输出：graph.invoke() 的参数字典（recursion_limit, stream_mode 等）
"""

# TradingAgents/graph/propagation.py

from typing import Dict, Any, List, Optional
from tradingagents.agents.utils.agent_states import (
    AgentState,
    InvestDebateState,
    RiskDebateState,
)


class Propagator:
    """LangGraph 初始状态构建器和执行参数配置器。

    职责：
      1. create_initial_state(): 从原始输入参数构建符合 AgentState schema 的完整初始状态
      2. get_graph_args(): 构建图执行时的配置参数（递归限制、回调等）

    设计要点：
      - 所有字段必须显式初始化 —— LangGraph 的 TypedDict 状态要求访问前字段已存在，
        否则 KeyError 会中断节点执行
      - 嵌套子状态（InvestDebateState / RiskDebateState）也在此处创建空实例
      - past_context 是唯一从外部注入的非空字段（来自记忆日志的历史教训）
    """

    def __init__(self, max_recur_limit=100):
        """初始化传播器。

        Args:
            max_recur_limit: LangGraph 执行的最大递归步数限制。
                防止工具循环或辩论死循环导致无限执行。
                默认100步对大多数场景足够（4个分析师×3轮工具调用×2轮辩论 ≈ 30-50步）。
                如果遇到 RecursionError 可以调高此值。
        """
        self.max_recur_limit = max_recur_limit

    def create_initial_state(
        self,
        company_name: str,
        trade_date: str,
        asset_type: str = "stock",
        past_context: str = "",
    ) -> Dict[str, Any]:
        """构建 LangGraph 的完整初始状态字典。

        这是图执行的起点 —— graph.invoke(initial_state) 传入的就是这个返回值。
        后续每个节点函数接收到的 state 都是基于这个初始值的逐步更新版本。

        初始状态的设计原则：
          - 字符串字段初始化为 ""（空字符串）：下游节点用 len() 或 if 判断是否有内容
          - count 字段初始化为 0：被 conditional_logic 的路由函数用来判断轮次
          - messages 初始化为 [("human", company_name)]：模拟用户的首次输入，
            让第一个分析师节点有「用户消息」可以响应
          - past_context 可能非空：包含历史决策教训，是系统的「长期记忆」

        为什么 InvestDebateState / RiskDebateState 要用构造函数而非普通 dict？
          - 类型安全：TypedDict 构造函数会在运行时做基本的键存在性检查
          - IDE 支持：IDE 能推断出嵌套字段的名称，提供自动补全
          - 文档化：明确表达「这是一个 InvestDebateState 类型的对象」

        Args:
            company_name: 目标公司 ticker 或名称（如 "AAPL"）
            trade_date: 交易日期字符串（如 "2024-01-15"）
            asset_type: 资产类型，"stock"（默认）或 "crypto"
            past_context: 从记忆日志获取的历史上下文字符串，
                          包含同 ticker 历史决策和跨 ticker 教训

        Returns:
            符合 AgentState schema 的完整初始状态字典
        """
        return {
            # ── 对话消息：以用户输入作为首条消息 ──
            "messages": [("human", company_name)],

            # ── 第1阶段：输入参数 ──
            "company_of_interest": company_name,
            "asset_type": asset_type,
            "trade_date": str(trade_date),

            # ── 跨轮次记忆注入（可能非空）──
            "past_context": past_context,

            # ── 第3阶段：投资辩论子状态（全部初始化为空）──
            "investment_debate_state": InvestDebateState(
                {
                    "bull_history": "",         # Bull 发言累计文本
                    "bear_history": "",         # Bear 发言累计文本
                    "history": "",              # 合并对话历史
                    "current_response": "",     # 最新一轮发言内容
                    "judge_decision": "",       # 裁判结论（终止时填写）
                    "count": 0,                 # 已发言次数
                }
            ),

            # ── 第4阶段：风险讨论子状态（全部初始化为空）──
            "risk_debate_state": RiskDebateState(
                {
                    "aggressive_history": "",           # 激进方累计发言
                    "conservative_history": "",         # 保守方累计发言
                    "neutral_history": "",              # 中立方累计发言
                    "history": "",                      # 合并对话历史
                    "latest_speaker": "",               # 上次发言者标识
                    "current_aggressive_response": "",  # 激进方最新回复
                    "current_conservative_response": "",# 保守方最新回复
                    "current_neutral_response": "",     # 中立最新回复
                    "judge_decision": "",               # 裁判结论
                    "count": 0,                         # 已发言次数
                }
            ),

            # ── 第2阶段：研究报告（4路并行产出，初始全空）──
            "market_report": "",
            "fundamentals_report": "",
            "sentiment_report": "",
            "news_report": "",
        }

    def get_graph_args(self, callbacks: Optional[List] = None) -> Dict[str, Any]:
        """构建 LangGraph graph.invoke() / graph.stream() 的执行参数。

        这些参数控制图的运行时行为：

        stream_mode="values":
          - 返回每一步执行后的**完整状态快照**（而非仅增量 delta）
          - debug 模式下用于逐节点观察状态变化
          - 非 debug 模式下 invoke 不受此参数影响（invoke 总是返回最终状态）

        recursion_limit:
          - 防止无限循环的安全阀
          - 工具循环（ReAct）+ 辩论轮转都可能产生大量步骤
          - 超限时 LangGraph 抛 GraphRecursionError
          - 默认 100 步 = 4分析师 × ~5轮工具 × 2轮辩论 × 2方 ≈ 有余量

        callbacks:
          - 用于追踪工具执行、token 用量等运行时指标
          - 注意：LLM 回调已在 LLM 构造时注入，这里的 callbacks 主要给工具执行用

        Args:
            callbacks: 可选的回调处理器列表（用于工具执行追踪等）

        Returns:
            可直接传入 graph.invoke(**args) 或 graph.stream(**args) 的参数字典
        """
        config = {"recursion_limit": self.max_recur_limit}
        if callbacks:
            config["callbacks"] = callbacks
        return {
            "stream_mode": "values",
            "config": config,
        }
