# TradingAgents/graph/setup.py

from typing import Dict, Any
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph, START
from langgraph.prebuilt import ToolNode

from tradingagents.agents import *
from tradingagents.agents.utils.agent_states import AgentState

from .conditional_logic import ConditionalLogic

# Map analyst key to (display name, factory function, clear name)
_ANALYST_MAP = {
    "odds": ("Odds Analyst", create_odds_analyst, "Msg Clear Odds"),
    "social": ("Social Analyst", create_social_media_analyst, "Msg Clear Social"),
    "news": ("News Analyst", create_news_analyst, "Msg Clear News"),
    "event": ("Event Analyst", create_event_analyst, "Msg Clear Event"),
}


class GraphSetup:
    """Handles the setup and configuration of the agent graph."""

    def __init__(
        self,
        quick_thinking_llm: ChatOpenAI,
        deep_thinking_llm: ChatOpenAI,
        tool_nodes: Dict[str, ToolNode],
        bull_memory,
        bear_memory,
        timing_memory,
        trader_memory,
        invest_judge_memory,
        risk_manager_memory,
        conditional_logic: ConditionalLogic,
    ):
        """Initialize with required components."""
        self.quick_thinking_llm = quick_thinking_llm
        self.deep_thinking_llm = deep_thinking_llm
        self.tool_nodes = tool_nodes
        self.bull_memory = bull_memory
        self.bear_memory = bear_memory
        self.timing_memory = timing_memory
        self.trader_memory = trader_memory
        self.invest_judge_memory = invest_judge_memory
        self.risk_manager_memory = risk_manager_memory
        self.conditional_logic = conditional_logic

    def setup_graph(
        self, selected_analysts=["odds", "social", "news", "event"]
    ):
        """Set up and compile the agent workflow graph.

        Args:
            selected_analysts (list): List of analyst types to include. Options are:
                - "odds": Odds analyst
                - "social": Social media analyst
                - "news": News analyst
                - "event": Event analyst
        """
        if len(selected_analysts) == 0:
            raise ValueError("Trading Agents Graph Setup Error: no analysts selected!")

        # Validate analyst keys
        for key in selected_analysts:
            if key not in _ANALYST_MAP:
                raise ValueError(
                    f"Unknown analyst type '{key}'. Valid options: {list(_ANALYST_MAP.keys())}"
                )

        # Create analyst nodes
        analyst_nodes = {}
        delete_nodes = {}
        tool_nodes = {}

        for key in selected_analysts:
            display_name, factory, clear_name = _ANALYST_MAP[key]
            analyst_nodes[key] = factory(self.quick_thinking_llm)
            delete_nodes[key] = create_msg_delete()
            tool_nodes[key] = self.tool_nodes[key]

        # Create researcher and manager nodes
        yes_advocate_node = create_yes_advocate(
            self.quick_thinking_llm, self.bull_memory
        )
        no_advocate_node = create_no_advocate(
            self.quick_thinking_llm, self.bear_memory
        )
        timing_advocate_node = create_timing_advocate(
            self.quick_thinking_llm, self.timing_memory
        )
        research_manager_node = create_research_manager(
            self.deep_thinking_llm, self.invest_judge_memory
        )
        trader_node = create_trader(self.quick_thinking_llm, self.trader_memory)

        # Create risk analysis nodes
        aggressive_analyst = create_aggressive_debator(self.quick_thinking_llm)
        neutral_analyst = create_neutral_debator(self.quick_thinking_llm)
        conservative_analyst = create_conservative_debator(self.quick_thinking_llm)
        risk_manager_node = create_risk_manager(
            self.deep_thinking_llm, self.risk_manager_memory
        )

        # Create workflow
        workflow = StateGraph(AgentState)

        # Add analyst nodes to the graph
        for key in selected_analysts:
            display_name, _, clear_name = _ANALYST_MAP[key]
            workflow.add_node(display_name, analyst_nodes[key])
            workflow.add_node(clear_name, delete_nodes[key])
            workflow.add_node(f"tools_{key}", tool_nodes[key])

        # Add researcher, manager, trader, and risk nodes
        workflow.add_node("YES Advocate", yes_advocate_node)
        workflow.add_node("NO Advocate", no_advocate_node)
        workflow.add_node("Timing Advocate", timing_advocate_node)
        workflow.add_node("Research Manager", research_manager_node)
        workflow.add_node("Trader", trader_node)
        workflow.add_node("Aggressive Analyst", aggressive_analyst)
        workflow.add_node("Neutral Analyst", neutral_analyst)
        workflow.add_node("Conservative Analyst", conservative_analyst)
        workflow.add_node("Risk Judge", risk_manager_node)

        # Define edges
        # Start with the first analyst
        first_key = selected_analysts[0]
        first_display_name = _ANALYST_MAP[first_key][0]
        workflow.add_edge(START, first_display_name)

        # Connect analysts in sequence using conditional logic
        for i, key in enumerate(selected_analysts):
            display_name, _, clear_name = _ANALYST_MAP[key]
            tools_node = f"tools_{key}"
            cond_fn = getattr(self.conditional_logic, f"should_continue_{key}")

            workflow.add_conditional_edges(
                display_name,
                cond_fn,
                [tools_node, clear_name],
            )
            workflow.add_edge(tools_node, display_name)

            # Connect clear node to next analyst or to YES Advocate
            if i < len(selected_analysts) - 1:
                next_display_name = _ANALYST_MAP[selected_analysts[i + 1]][0]
                workflow.add_edge(clear_name, next_display_name)
            else:
                workflow.add_edge(clear_name, "YES Advocate")

        # 3-way investment debate: YES → NO → Timing → YES (cycle until done)
        workflow.add_conditional_edges(
            "YES Advocate",
            self.conditional_logic.should_continue_debate,
            {
                "NO Advocate": "NO Advocate",
                "Research Manager": "Research Manager",
            },
        )
        workflow.add_conditional_edges(
            "NO Advocate",
            self.conditional_logic.should_continue_debate,
            {
                "Timing Advocate": "Timing Advocate",
                "Research Manager": "Research Manager",
            },
        )
        workflow.add_conditional_edges(
            "Timing Advocate",
            self.conditional_logic.should_continue_debate,
            {
                "YES Advocate": "YES Advocate",
                "Research Manager": "Research Manager",
            },
        )

        workflow.add_edge("Research Manager", "Trader")
        workflow.add_edge("Trader", "Aggressive Analyst")

        # 3-way risk debate
        workflow.add_conditional_edges(
            "Aggressive Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Conservative Analyst": "Conservative Analyst",
                "Risk Judge": "Risk Judge",
            },
        )
        workflow.add_conditional_edges(
            "Conservative Analyst",
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
                "Aggressive Analyst": "Aggressive Analyst",
                "Risk Judge": "Risk Judge",
            },
        )

        workflow.add_edge("Risk Judge", END)

        # Compile and return
        return workflow.compile()
