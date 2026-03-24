# TradingAgents/graph/setup.py

from typing import Dict, Any
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph, START
from langgraph.prebuilt import ToolNode

from tradingagents.agents import *
from tradingagents.agents.utils.agent_states import AgentState

from .conditional_logic import ConditionalLogic


class GraphSetup:
    """Handles the setup and configuration of the agent graph."""

    def __init__(
        self,
        quick_thinking_llm: ChatOpenAI,
        deep_thinking_llm: ChatOpenAI,
        tool_nodes: Dict[str, ToolNode],
        bull_memory,
        bear_memory,
        trader_memory,
        invest_judge_memory,
        portfolio_manager_memory,
        conditional_logic: ConditionalLogic,
        role_llms: Dict[str, Any] | None = None,
    ):
        """Initialize with required components."""
        self.quick_thinking_llm = quick_thinking_llm
        self.deep_thinking_llm = deep_thinking_llm
        self.role_llms = role_llms or {}
        self.tool_nodes = tool_nodes
        self.bull_memory = bull_memory
        self.bear_memory = bear_memory
        self.trader_memory = trader_memory
        self.invest_judge_memory = invest_judge_memory
        self.portfolio_manager_memory = portfolio_manager_memory
        self.conditional_logic = conditional_logic
        self.market_analyst_llm = self._get_role_llm("market", self.quick_thinking_llm)
        self.social_analyst_llm = self._get_role_llm("social", self.quick_thinking_llm)
        self.news_analyst_llm = self._get_role_llm("news", self.quick_thinking_llm)
        self.fundamentals_analyst_llm = self._get_role_llm(
            "fundamentals", self.quick_thinking_llm
        )
        self.factor_rules_analyst_llm = self._get_role_llm(
            "factor_rules", self.quick_thinking_llm
        )
        self.macro_analyst_llm = self._get_role_llm("macro", self.quick_thinking_llm)
        self.bull_researcher_llm = self._get_role_llm(
            "bull_researcher", self.quick_thinking_llm
        )
        self.bear_researcher_llm = self._get_role_llm(
            "bear_researcher", self.quick_thinking_llm
        )
        self.research_manager_llm = self._get_role_llm(
            "research_manager", self.deep_thinking_llm
        )
        self.trader_llm = self._get_role_llm("trader", self.quick_thinking_llm)
        self.aggressive_analyst_llm = self._get_role_llm(
            "aggressive_analyst", self.quick_thinking_llm
        )
        self.neutral_analyst_llm = self._get_role_llm(
            "neutral_analyst", self.quick_thinking_llm
        )
        self.conservative_analyst_llm = self._get_role_llm(
            "conservative_analyst", self.quick_thinking_llm
        )
        self.portfolio_manager_llm = self._get_role_llm(
            "portfolio_manager", self.deep_thinking_llm
        )

    def _get_role_llm(self, role: str, fallback_llm: ChatOpenAI):
        return self.role_llms.get(role, fallback_llm)

    def _get_continue_handler(self, analyst_type: str):
        specific_handler = getattr(
            self.conditional_logic,
            f"should_continue_{analyst_type}",
            None,
        )
        if specific_handler is not None:
            return specific_handler

        def default_handler(state: AgentState):
            messages = state["messages"]
            last_message = messages[-1]
            if getattr(last_message, "tool_calls", None):
                return f"tools_{analyst_type}"
            return f"Msg Clear {analyst_type.capitalize()}"

        return default_handler

    def setup_graph(
        self, selected_analysts=["market", "social", "news", "fundamentals", "macro"]
    ):
        """Set up and compile the agent workflow graph.

        Args:
            selected_analysts (list): List of analyst types to include. Options are:
                - "market": Market analyst
                - "social": Social media analyst
                - "news": News analyst
                - "fundamentals": Fundamentals analyst
                - "factor_rules": Factor rule analyst
                - "macro": Macro analyst
        """
        if len(selected_analysts) == 0:
            raise ValueError("Trading Agents Graph Setup Error: no analysts selected!")

        # Create analyst nodes
        analyst_nodes = {}
        delete_nodes = {}
        tool_nodes = {}

        if "market" in selected_analysts:
            analyst_nodes["market"] = create_market_analyst(
                self.market_analyst_llm
            )
            delete_nodes["market"] = create_msg_delete()
            tool_nodes["market"] = self.tool_nodes["market"]

        if "social" in selected_analysts:
            analyst_nodes["social"] = create_social_media_analyst(
                self.social_analyst_llm
            )
            delete_nodes["social"] = create_msg_delete()
            tool_nodes["social"] = self.tool_nodes["social"]

        if "news" in selected_analysts:
            analyst_nodes["news"] = create_news_analyst(
                self.news_analyst_llm
            )
            delete_nodes["news"] = create_msg_delete()
            tool_nodes["news"] = self.tool_nodes["news"]

        if "fundamentals" in selected_analysts:
            analyst_nodes["fundamentals"] = create_fundamentals_analyst(
                self.fundamentals_analyst_llm
            )
            delete_nodes["fundamentals"] = create_msg_delete()
            tool_nodes["fundamentals"] = self.tool_nodes["fundamentals"]

        if "factor_rules" in selected_analysts:
            analyst_nodes["factor_rules"] = create_factor_rule_analyst(
                self.factor_rules_analyst_llm
            )
            delete_nodes["factor_rules"] = create_msg_delete()

        if "macro" in selected_analysts:
            analyst_nodes["macro"] = create_macro_analyst(self.macro_analyst_llm)
            delete_nodes["macro"] = create_msg_delete()
            tool_nodes["macro"] = self.tool_nodes["macro"]

        # Create researcher and manager nodes
        bull_researcher_node = create_bull_researcher(
            self.bull_researcher_llm, self.bull_memory
        )
        bear_researcher_node = create_bear_researcher(
            self.bear_researcher_llm, self.bear_memory
        )
        research_manager_node = create_research_manager(
            self.research_manager_llm, self.invest_judge_memory
        )
        trader_node = create_trader(self.trader_llm, self.trader_memory)

        # Create risk analysis nodes
        aggressive_analyst = create_aggressive_debator(self.aggressive_analyst_llm)
        neutral_analyst = create_neutral_debator(self.neutral_analyst_llm)
        conservative_analyst = create_conservative_debator(
            self.conservative_analyst_llm
        )
        portfolio_manager_node = create_portfolio_manager(
            self.portfolio_manager_llm, self.portfolio_manager_memory
        )

        # Create workflow
        workflow = StateGraph(AgentState)

        # Add analyst nodes to the graph
        for analyst_type, node in analyst_nodes.items():
            workflow.add_node(f"{analyst_type.capitalize()} Analyst", node)
            workflow.add_node(
                f"Msg Clear {analyst_type.capitalize()}", delete_nodes[analyst_type]
            )
            if analyst_type in tool_nodes:
                workflow.add_node(f"tools_{analyst_type}", tool_nodes[analyst_type])

        # Add other nodes
        workflow.add_node("Bull Researcher", bull_researcher_node)
        workflow.add_node("Bear Researcher", bear_researcher_node)
        workflow.add_node("Research Manager", research_manager_node)
        workflow.add_node("Trader", trader_node)
        workflow.add_node("Aggressive Analyst", aggressive_analyst)
        workflow.add_node("Neutral Analyst", neutral_analyst)
        workflow.add_node("Conservative Analyst", conservative_analyst)
        workflow.add_node("Portfolio Manager", portfolio_manager_node)

        # Define edges
        # Start with the first analyst
        first_analyst = selected_analysts[0]
        workflow.add_edge(START, f"{first_analyst.capitalize()} Analyst")

        # Connect analysts in sequence
        for i, analyst_type in enumerate(selected_analysts):
            current_analyst = f"{analyst_type.capitalize()} Analyst"
            current_tools = f"tools_{analyst_type}"
            current_clear = f"Msg Clear {analyst_type.capitalize()}"

            # Add conditional edges for current analyst
            workflow.add_conditional_edges(
                current_analyst,
                self._get_continue_handler(analyst_type),
                [current_tools, current_clear]
                if analyst_type in tool_nodes
                else [current_clear],
            )
            if analyst_type in tool_nodes:
                workflow.add_edge(current_tools, current_analyst)

            # Connect to next analyst or to Bull Researcher if this is the last analyst
            if i < len(selected_analysts) - 1:
                next_analyst = f"{selected_analysts[i+1].capitalize()} Analyst"
                workflow.add_edge(current_clear, next_analyst)
            else:
                workflow.add_edge(current_clear, "Bull Researcher")

        # Add remaining edges
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

        workflow.add_edge("Portfolio Manager", END)

        # Compile and return
        return workflow.compile()
