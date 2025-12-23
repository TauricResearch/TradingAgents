# -*- coding: utf-8 -*-
# TradingAgentsX/graph/setup.py

from typing import Dict, Any
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph, START
from langgraph.prebuilt import ToolNode

from tradingagents.agents import *
from tradingagents.agents.utils.agent_states import AgentState

from .conditional_logic import ConditionalLogic


class GraphSetup:
    """
    處理代理圖的設定和組態。
    這個類別負責根據所選的分析師和設定來建立和連接圖中的所有節點。
    """

    def __init__(
        self,
        quick_thinking_llm: ChatOpenAI,
        deep_thinking_llm: ChatOpenAI,
        tool_nodes: Dict[str, ToolNode],
        bull_memory,
        bear_memory,
        trader_memory,
        invest_judge_memory,
        risk_manager_memory,
        conditional_logic: ConditionalLogic,
        language: str = "zh-TW",
    ):
        """
        使用必要的組件進行初始化。

        Args:
            quick_thinking_llm (ChatOpenAI): 用於快速任務的 LLM。
            deep_thinking_llm (ChatOpenAI): 用於深度分析的 LLM。
            tool_nodes (Dict[str, ToolNode]): 包含工具節點的字典。
            bull_memory: 看漲研究員的記憶體。
            bear_memory: 看跌研究員的記憶體。
            trader_memory: 交易員的記憶體。
            invest_judge_memory: 投資裁判的記憶體。
            risk_manager_memory: 風險管理者的記憶體。
            conditional_logic (ConditionalLogic): 處理圖中條件分支的邏輯。
            language (str): 報告語言 ('en' 或 'zh-TW')。
        """
        self.quick_thinking_llm = quick_thinking_llm
        self.deep_thinking_llm = deep_thinking_llm
        self.tool_nodes = tool_nodes
        self.bull_memory = bull_memory
        self.bear_memory = bear_memory
        self.trader_memory = trader_memory
        self.invest_judge_memory = invest_judge_memory
        self.risk_manager_memory = risk_manager_memory
        self.conditional_logic = conditional_logic
        self.language = language

    def setup_graph(
        self, selected_analysts=["market", "social", "news", "fundamentals"]
    ):
        """
        設定並編譯代理工作流程圖。

        Args:
            selected_analysts (list): 要包含的分析師類型列表。選項包括：
                - "market": 市場分析師
                - "social": 社群媒體分析師
                - "news": 新聞分析師
                - "fundamentals": 基本面分析師
        
        Returns:
            CompiledGraph: 編譯完成的 langgraph 圖。
        """
        if len(selected_analysts) == 0:
            raise ValueError("交易代理圖設定錯誤：未選擇任何分析師！")

        # 建立分析師節點
        analyst_nodes = {}
        delete_nodes = {}
        tool_nodes = {}

        if "market" in selected_analysts:
            analyst_nodes["market"] = create_market_analyst(
                self.quick_thinking_llm, self.language
            )
            delete_nodes["market"] = create_msg_delete()
            tool_nodes["market"] = self.tool_nodes["market"]

        if "social" in selected_analysts:
            analyst_nodes["social"] = create_social_media_analyst(
                self.quick_thinking_llm, self.language
            )
            delete_nodes["social"] = create_msg_delete()
            tool_nodes["social"] = self.tool_nodes["social"]

        if "news" in selected_analysts:
            analyst_nodes["news"] = create_news_analyst(
                self.quick_thinking_llm, self.language
            )
            delete_nodes["news"] = create_msg_delete()
            tool_nodes["news"] = self.tool_nodes["news"]

        if "fundamentals" in selected_analysts:
            analyst_nodes["fundamentals"] = create_fundamentals_analyst(
                self.quick_thinking_llm, self.language
            )
            delete_nodes["fundamentals"] = create_msg_delete()
            tool_nodes["fundamentals"] = self.tool_nodes["fundamentals"]

        # 建立研究員和管理者節點
        bull_researcher_node = create_bull_researcher(
            self.quick_thinking_llm, self.bull_memory, self.language
        )
        bear_researcher_node = create_bear_researcher(
            self.quick_thinking_llm, self.bear_memory, self.language
        )
        research_manager_node = create_research_manager(
            self.deep_thinking_llm, self.invest_judge_memory, self.language
        )
        trader_node = create_trader(self.quick_thinking_llm, self.trader_memory, self.language)

        # 建立風險分析節點
        risky_analyst = create_risky_debator(self.quick_thinking_llm, self.language)
        neutral_analyst = create_neutral_debator(self.quick_thinking_llm, self.language)
        safe_analyst = create_safe_debator(self.quick_thinking_llm, self.language)
        risk_manager_node = create_risk_manager(
            self.deep_thinking_llm, self.risk_manager_memory, self.language
        )

        # 建立工作流程
        workflow = StateGraph(AgentState)

        # 將分析師節點新增到圖中
        for analyst_type, node in analyst_nodes.items():
            workflow.add_node(f"{analyst_type.capitalize()} Analyst", node)
            workflow.add_node(
                f"Msg Clear {analyst_type.capitalize()}", delete_nodes[analyst_type]
            )
            workflow.add_node(f"tools_{analyst_type}", tool_nodes[analyst_type])

        # 新增其他節點
        workflow.add_node("Bull Researcher", bull_researcher_node)
        workflow.add_node("Bear Researcher", bear_researcher_node)
        workflow.add_node("Research Manager", research_manager_node)
        workflow.add_node("Trader", trader_node)
        workflow.add_node("Risky Analyst", risky_analyst)
        workflow.add_node("Neutral Analyst", neutral_analyst)
        workflow.add_node("Safe Analyst", safe_analyst)
        workflow.add_node("Risk Judge", risk_manager_node)

        # 定義邊
        # 從第一個分析師開始
        first_analyst = selected_analysts[0]
        workflow.add_edge(START, f"{first_analyst.capitalize()} Analyst")

        # 依次連接分析師
        for i, analyst_type in enumerate(selected_analysts):
            current_analyst = f"{analyst_type.capitalize()} Analyst"
            current_tools = f"tools_{analyst_type}"
            current_clear = f"Msg Clear {analyst_type.capitalize()}"

            # 為當前分析師新增條件邊
            workflow.add_conditional_edges(
                current_analyst,
                getattr(self.conditional_logic, f"should_continue_{analyst_type}"),
                [current_tools, current_clear],
            )
            workflow.add_edge(current_tools, current_analyst)

            # 連接到下一個分析師，如果是最後一個分析師，則連接到看漲研究員
            if i < len(selected_analysts) - 1:
                next_analyst = f"{selected_analysts[i+1].capitalize()} Analyst"
                workflow.add_edge(current_clear, next_analyst)
            else:
                workflow.add_edge(current_clear, "Bull Researcher")

        # 新增剩餘的邊
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
        workflow.add_edge("Research Manager", "Trader")
        workflow.add_edge("Trader", "Risky Analyst")
        workflow.add_conditional_edges(
            "Risky Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Safe Analyst": "Safe Analyst",
                "Risk Judge": "Risk Judge",
            },
        )
        workflow.add_conditional_edges(
            "Safe Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Neutral Analyst": "Neutral Analyst",
                "Risk Judge": "Risk Judge",
            },
        )
        workflow.add_conditional_edges(
            "Neutral Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Risky Analyst": "Risky Analyst",
                "Risk Judge": "Risk Judge",
            },
        )

        workflow.add_edge("Risk Judge", END)

        # 編譯並返回
        return workflow.compile()