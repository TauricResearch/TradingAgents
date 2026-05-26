# TradingAgents/graph/setup.py

from typing import Any, Dict
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from tradingagents.agents import *
from tradingagents.agents.utils.agent_states import AgentState

from .analyst_execution import build_analyst_execution_plan
from .conditional_logic import ConditionalLogic


class GraphSetup:
    """负责构建 LangGraph StateGraph 的装配类。

    将分析师、多空辩论、风险分析等阶段串联成完整的工作流。
    整个图通过 setup_graph() 一次性构建并编译返回。
    """

    def __init__(
        self,
        quick_thinking_llm: Any,
        deep_thinking_llm: Any,
        tool_nodes: Dict[str, ToolNode],
        conditional_logic: ConditionalLogic,
        analyst_concurrency_limit: int = 1,
    ):
        """初始化图装配所需组件。

        Args:
            quick_thinking_llm: 快思考模型（用于分析师、研究员、交易员等）
            deep_thinking_llm: 深思考模型（用于研究经理、投资组合经理）
            tool_nodes: 各分析师对应的 ToolNode 字典，key 如 "market"、"social" 等
            conditional_logic: 条件边逻辑实例，控制图中何时进入下一节点
            analyst_concurrency_limit: 分析师并发数限制（预留，当前未使用）
        """
        self.quick_thinking_llm = quick_thinking_llm
        self.deep_thinking_llm = deep_thinking_llm
        self.tool_nodes = tool_nodes
        self.conditional_logic = conditional_logic
        self.analyst_concurrency_limit = analyst_concurrency_limit

    def setup_graph(
        self, selected_analysts=["market", "social", "news", "fundamentals"]
    ):
        """构建并编译 LangGraph StateGraph 工作流。

        工作流分四个阶段：
        1. 分析师阶段（Market → Social → News → Fundamentals）
        2. 多空辩论阶段（Bull/Bear Researcher 来回辩论）
        3. 风险分析阶段（Aggressive → Conservative → Neutral 三角辩论）
        4. 决策阶段（Research Manager → Trader → Portfolio Manager → END）

        Args:
            selected_analysts: 要包含的分析师类型列表。
                可选值: "market" / "social" / "news" / "fundamentals"
        """
        # 根据 selected_analysts 生成执行计划（顺序 + 并发配置）
        plan = build_analyst_execution_plan(
            selected_analysts,
            concurrency_limit=self.analyst_concurrency_limit,
        )

        # 分析师工厂方法：lambda 延迟实例化，避免在图构建时创建 Agent
        analyst_factories = {
            "market": lambda: create_market_analyst(self.quick_thinking_llm),
            "social": lambda: create_sentiment_analyst(self.quick_thinking_llm),
            "news": lambda: create_news_analyst(self.quick_thinking_llm),
            "fundamentals": lambda: create_fundamentals_analyst(self.quick_thinking_llm),
        }

        # ====== 创建各节点实例 ======
        # 多空研究员（快思考）
        bull_researcher_node = create_bull_researcher(self.quick_thinking_llm)
        bear_researcher_node = create_bear_researcher(self.quick_thinking_llm)
        # 研究经理（深思考）：汇总辩论结果
        research_manager_node = create_research_manager(self.deep_thinking_llm)
        # 交易员（快思考）：执行交易决策
        trader_node = create_trader(self.quick_thinking_llm)

        # 风险分析师三角（快思考）
        aggressive_analyst = create_aggressive_debator(self.quick_thinking_llm)
        neutral_analyst = create_neutral_debator(self.quick_thinking_llm)
        conservative_analyst = create_conservative_debator(self.quick_thinking_llm)
        # 投资组合经理（深思考）：综合风险分析做最终仓位决策
        portfolio_manager_node = create_portfolio_manager(self.deep_thinking_llm)

        # ====== 构建 StateGraph ======
        workflow = StateGraph(AgentState)

        # ---- 阶段1：添加分析师节点 ----
        # 每个分析师有3个关联节点：agent_node（分析）、tool_node（工具）、clear_node（清消息）
        for spec in plan.specs:
            workflow.add_node(spec.agent_node, analyst_factories[spec.key]())
            workflow.add_node(spec.clear_node, create_msg_delete())
            workflow.add_node(spec.tool_node, self.tool_nodes[spec.key])

        # ---- 阶段1：添加研究员和交易员节点 ----
        workflow.add_node("Bull Researcher", bull_researcher_node)
        workflow.add_node("Bear Researcher", bear_researcher_node)
        workflow.add_node("Research Manager", research_manager_node)
        workflow.add_node("Trader", trader_node)

        # ---- 阶段1：添加风险分析师节点 ----
        workflow.add_node("Aggressive Analyst", aggressive_analyst)
        workflow.add_node("Neutral Analyst", neutral_analyst)
        workflow.add_node("Conservative Analyst", conservative_analyst)
        workflow.add_node("Portfolio Manager", portfolio_manager_node)

        # ====== 定义边 ======
        # 起始边：从 START 到第一位分析师
        workflow.add_edge(START, plan.specs[0].agent_node)

        # ---- 阶段1：串联各分析师 ----
        # 每位分析师的流转逻辑：
        #   agent_node 执行后 → conditional_edges 判断
        #     ├─ 有 tool_calls → 去 tool_node → 回到 agent_node（继续分析）
        #     └─ 无 tool_calls → 去 clear_node（清消息）
        #         └─ 下一位分析师 或 Bull Researcher（最后一位时）
        for i, spec in enumerate(plan.specs):
            current_analyst = spec.agent_node
            current_tools = spec.tool_node
            current_clear = spec.clear_node

            workflow.add_conditional_edges(
                current_analyst,
                getattr(self.conditional_logic, f"should_continue_{spec.key}"),
                {current_tools: current_tools, current_clear: current_clear},
            )
            workflow.add_edge(current_tools, current_analyst)

            if i < len(plan.specs) - 1:
                workflow.add_edge(current_clear, plan.specs[i + 1].agent_node)
            else:
                workflow.add_edge(current_clear, "Bull Researcher")

        # ---- 阶段2：多空辩论 ----
        # Bull/Bear 来回辩论，直到达到 max_debate_rounds 上限后进入 Research Manager
        workflow.add_conditional_edges(
            "Bull Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Bear Researcher": "Bear Researcher",
                "Research Manager": "Research Manager",
            },
        )
        workflow.add_conditional_edges(
            "Bear Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Bull Researcher": "Bull Researcher",
                "Research Manager": "Research Manager",
            },
        )

        # ---- 阶段3：研究经理汇总 → 交易员执行 ----
        workflow.add_edge("Research Manager", "Trader")

        # ---- 阶段4：风险分析（三角辩论）----
        # Aggressive → Conservative → Neutral →（循环）→ Portfolio Manager
        # 由 risk_debate_state["count"] 和 latest_speaker 共同决定流转方向
        workflow.add_edge("Trader", "Aggressive Analyst")

        workflow.add_conditional_edges(
            "Aggressive Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Conservative Analyst": "Conservative Analyst",
                "Portfolio Manager": "Portfolio Manager",
            },
        )
        workflow.add_conditional_edges(
            "Conservative Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Neutral Analyst": "Neutral Analyst",
                "Portfolio Manager": "Portfolio Manager",
            },
        )
        workflow.add_conditional_edges(
            "Neutral Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Aggressive Analyst": "Aggressive Analyst",
                "Portfolio Manager": "Portfolio Manager",
            },
        )

        # 最终边：Portfolio Manager → 结束
        workflow.add_edge("Portfolio Manager", END)

        return workflow
