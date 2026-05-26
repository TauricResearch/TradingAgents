"""
图条件路由逻辑（Conditional Edge Routing）

在项目中的角色：
  - LangGraph 有向图中所有「条件边（conditional edge）」的判断函数集合
  - 决定「执行完当前节点后，下一步该去哪个节点」
  - 是图的「交通指挥员」—— 控制工具循环、辩论轮次、角色轮换

两类路由逻辑：

  ┌─────────────────────────────────────────────┐
  │ 第1类：工具循环控制（4个 should_continue_*）    │
  │   判断 LLM 是否还要继续调用工具               │
  │   用法：AnalystNode → [本函数] → ToolNode / 下游│
  │   逻辑：最后一条消息有 tool_calls？→ 继续工具节点 │
  │         否则 → 进入消息清理节点（Msg Clear *）   │
  ├─────────────────────────────────────────────┤
  │ 第2类：辩论轮次控制（2个 should_continue_*）     │
  │   控制 Agent 之间的多轮对话何时终止            │
  │   用法：DebateNode → [本函数] → 下一发言者 / 裁判│
  │   逻辑：轮次未超限 → 按规则轮换到下一个角色      │
  │         轮次超限 → 跳转到裁判/汇总节点           │
  └─────────────────────────────────────────────┘

在 GraphSetup 中如何被使用：
    graph.add_conditional_edges(
        "market_analyst",                    # 源节点
        self.conditional_logic.should_continue_market,  # 路由函数 ← 本文件
        {
            "tools_market": "tools_market",   # 返回值 → 目标节点
            "Msg Clear Market": "msg_clear_market",
        }
    )
"""

# TradingAgents/graph/conditional_logic.py

from tradingagents.agents.utils.agent_states import AgentState


class ConditionalLogic:
    """LangGraph 条件边的路由逻辑集合。

    将所有路由判断集中到一个类中，好处：
      - 图构建代码（GraphSetup）更清晰 —— 只需传入方法引用
      - 路由参数（max_debate_rounds 等）集中管理
      - 方便单元测试 —— 可以独立测试每个路由函数

    设计模式：
      - 策略模式（Strategy Pattern）：每个方法是一个路由策略，
        LangGraph 的 conditional_edge 机制负责调用并按返回值分发
    """

    def __init__(self, max_debate_rounds=1, max_risk_discuss_rounds=1):
        """初始化路由参数。

        Args:
            max_debate_rounds: 投资辩论最大轮次（Bull↔Bear 各发言一次 = 1 轮）
            max_risk_discuss_rounds: 风险讨论最大轮次（三方各发言一次 = 1 轮）
        """
        self.max_debate_rounds = max_debate_rounds
        self.max_risk_discuss_rounds = max_risk_discuss_rounds

    # ══════════════════════════════════════════════
    # 第1类：工具循环控制 —— ReAct 模式的「动作循环」
    #
    # 每个 Analyst 节点执行后，LangGraph 调用这些函数判断：
    #   LLM 是输出了 tool_call（需要执行工具）？
    #   还是直接输出了文本（分析完成，进入下一阶段）？
    # ══════════════════════════════════════════════

    def should_continue_market(self, state: AgentState):
        """判断市场分析师是否需要继续调用工具。

        路由规则：
          - 最后一条 AIMessage 包含 tool_calls → 跳转到 tools_market 节点执行工具
          - 否则 → 跳转到 msg_clear_market 节点清理消息后进入下游

        这是标准的 LangGraph ReAct 循环模式：
          AnalystNode → [有tool_call?] → ToolNode → 回到 AnalystNode → [有tool_call?] → ...
                                                    ↓ 无tool_call
                                               Msg Clear → 下游节点

        Args:
            state: 当前全局状态

        Returns:
            字符串路由标签："tools_market" 或 "Msg Clear Market"
        """
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_market"
        return "Msg Clear Market"

    def should_continue_social(self, state: AgentState):
        """判断情绪分析师是否需要继续调用工具。

        与 should_continue_market 逻辑完全一致，只是目标节点不同。
        方法名保留 legacy 的 "social" 后缀以兼容已保存的配置文件中
        AnalystType.SOCIAL = "social" 的线值；但返回的路由标签使用了 v0.2.5
        重命名后的名称以匹配执行计划注册的节点名。

        Args:
            state: 当前全局状态

        Returns:
            "tools_social" 或 "Msg Clear Sentiment"
        """
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_social"
        return "Msg Clear Sentiment"

    def should_continue_news(self, state: AgentState):
        """判断新闻研究员是否需要继续调用工具。

        Args:
            state: 当前全局状态

        Returns:
            "tools_news" 或 "Msg Clear News"
        """
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_news"
        return "Msg Clear News"

    def should_continue_fundamentals(self, state: AgentState):
        """判断基本面分析师是否需要继续调用工具。

        这就是 fundamentals_analyst.py 所在的工具循环入口。
        当 LLM 在基本面节点发起 get_balance_sheet 等 tool_call 时，
        本函数返回 "tools_fundamentals"，LangGraph 将消息路由到
        对应的 ToolNode 执行实际的数据获取。

        Args:
            state: 当前全局状态

        Returns:
            "tools_fundamentals" 或 "Msg Clear Fundamentals"
        """
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_fundamentals"
        return "Msg Clear Fundamentals"

    # ══════════════════════════════════════════════
    # 第2类：辩论轮次控制 —— 多 Agent 对话的「主持人」
    #
    # 控制多个 Agent 之间的轮流发言和终止条件：
    #   投资辩论：Bull ↔ Bear 两方交替，超限后交 Research Manager 裁决
    #   风险讨论：Aggressive → Conservative → Neutral 三方轮转，超限后交 PM 汇总
    # ══════════════════════════════════════════════

    def should_continue_debate(self, state: AgentState) -> str:
        """判断投资辩论是否继续，以及下一步该谁发言。

        辩论结构：两方对抗（Bull Researcher vs Bear Researcher）
        轮次计算：count 每次发言 +1，双方各发言一次 = count += 2
        终止条件：count >= 2 * max_debate_rounds（默认 >= 2 即1轮就结束）

        轮换逻辑：
          - 上次是 Bull 发言（current_response 以 "Bull" 开头）→ 这次轮到 Bear
          - 否则 → 轮到 Bull
        终止时 → 跳转到 Research Manager 节点做最终裁决

        为什么用 current_response 前缀而不是存一个 speaker 字段？
          - 减少状态字段数量，复用已有的 current_response
          - 约定 Bull 的回复总是以 "Bull:" 开头（由 Prompt 保证）

        Args:
            state: 当前全局状态，需包含 investment_debate_state

        Returns:
            目标节点名字符串："Bear Researcher" / "Bull Researcher" / "Research Manager"
        """
        if (
            state["investment_debate_state"]["count"] >= 2 * self.max_debate_rounds
        ):  # 双方来回 max_debate_rounds 轮
            return "Research Manager"
        if state["investment_debate_state"]["current_response"].startswith("Bull"):
            return "Bear Researcher"
        return "Bull Researcher"

    def should_continue_risk_analysis(self, state: AgentState) -> str:
        """判断风险讨论是否继续，以及下一步该谁发言。

        讨论结构：三方博弈（Aggressive vs Conservative vs Neutral）
        轮次计算：count 每次发言 +1，三方各发言一次 = count += 3
        终止条件：count >= 3 * max_risk_discuss_rounds

        轮换逻辑（固定顺序链）：
          Aggressive → Conservative → Neutral → Aggressive → ...
          通过 latest_speaker 判断当前是谁，决定下一个

        为什么是固定顺序而非自由发言？
          - 避免混乱：固定顺序保证每方都有均等机会表达
          - 可控性：config 中调整 max_risk_discuss_rounds 即可控制总深度
          - Prompt 工程友好：每个角色知道「我是在回应谁」

        终止时 → 跳转到 Portfolio Manager 节点做最终决策

        Args:
            state: 当前全局状态，需包含 risk_debate_state

        Returns:
            目标节点名字符串："Conservative Analyst" / "Neutral Analyst" /
            "Aggressive Analyst" / "Portfolio Manager"
        """
        if (
            state["risk_debate_state"]["count"] >= 3 * self.max_risk_discuss_rounds
        ):  # 3 rounds of back-and-forth between 3 agents
            return "Portfolio Manager"
        if state["risk_debate_state"]["latest_speaker"].startswith("Aggressive"):
            return "Conservative Analyst"
        if state["risk_debate_state"]["latest_speaker"].startswith("Conservative"):
            return "Neutral Analyst"
        return "Aggressive Analyst"
