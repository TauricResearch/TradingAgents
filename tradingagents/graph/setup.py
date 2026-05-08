# TradingAgents/graph/setup.py

from typing import Any, List

from langgraph.graph import END, START, StateGraph

from tradingagents.agents import *
from tradingagents.agents.utils.agent_states import AgentState

from .conditional_logic import ConditionalLogic

# Canonical analyst key → display name mapping.  A single source of truth
# so that setup.py and conditional_logic.py never diverge.
ANALYST_NODE_NAMES = {
    "market": "Market Analyst",
    "social": "Social Analyst",
    "news": "News Analyst",
    "fundamentals": "Fundamentals Analyst",
}


class GraphSetup:
    """Handles the setup and configuration of the agent graph."""

    def __init__(
        self,
        quick_thinking_llm: Any,
        deep_thinking_llm: Any,
        conditional_logic: ConditionalLogic,
    ):
        self.quick_thinking_llm = quick_thinking_llm
        self.deep_thinking_llm = deep_thinking_llm
        self.conditional_logic = conditional_logic

    def setup_graph(self, selected_analysts: List[str] = None):
        """Set up and compile the agent workflow graph.

        Analysts run in parallel: all selected analyst nodes are fanned out from
        START and converge at Bull Researcher once every analyst has finished.
        Each analyst manages its own tool-calling loop internally, so no
        ToolNode or message-clearing nodes are needed.

        Args:
            selected_analysts: Analyst types to include. Options:
                "market", "social", "news", "fundamentals".
        """
        if selected_analysts is None:
            selected_analysts = ["market", "social", "news", "fundamentals"]
        if not selected_analysts:
            raise ValueError("Trading Agents Graph Setup Error: no analysts selected!")

        # Validate analyst keys early.
        unknown = set(selected_analysts) - set(ANALYST_NODE_NAMES)
        if unknown:
            raise ValueError(
                f"Unknown analyst type(s): {sorted(unknown)}. "
                f"Valid options: {sorted(ANALYST_NODE_NAMES)}"
            )

        # Build analyst factory map.
        analyst_factories = {
            "market": create_market_analyst,
            "social": create_social_media_analyst,
            "news": create_news_analyst,
            "fundamentals": create_fundamentals_analyst,
        }

        workflow = StateGraph(AgentState)

        # Add analyst nodes (parallel — each is self-contained).
        for key in selected_analysts:
            node_name = ANALYST_NODE_NAMES[key]
            workflow.add_node(node_name, analyst_factories[key](self.quick_thinking_llm))

        # Add researcher + manager nodes.
        workflow.add_node("Bull Researcher", create_bull_researcher(self.quick_thinking_llm))
        workflow.add_node("Bear Researcher", create_bear_researcher(self.quick_thinking_llm))
        workflow.add_node("Research Manager", create_research_manager(self.deep_thinking_llm))
        workflow.add_node("Trader", create_trader(self.quick_thinking_llm))

        # Add risk analysis nodes.
        workflow.add_node("Aggressive Analyst", create_aggressive_debator(self.quick_thinking_llm))
        workflow.add_node("Neutral Analyst", create_neutral_debator(self.quick_thinking_llm))
        workflow.add_node("Conservative Analyst", create_conservative_debator(self.quick_thinking_llm))
        workflow.add_node("Portfolio Manager", create_portfolio_manager(self.deep_thinking_llm))

        # Fan-out: START → all analysts in parallel.
        for key in selected_analysts:
            workflow.add_edge(START, ANALYST_NODE_NAMES[key])

        # Fan-in: each analyst → Bull Researcher.
        # LangGraph will not advance to Bull Researcher until every incoming
        # edge (i.e. every analyst) has completed.
        for key in selected_analysts:
            workflow.add_edge(ANALYST_NODE_NAMES[key], "Bull Researcher")

        # Research debate loop.
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

        # Risk debate loop.
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

        return workflow
