# TradingAgents/graph/setup.py

from typing import Any, List

from langgraph.graph import END, START, StateGraph

from tradingagents.agents import *
from tradingagents.agents.utils.agent_states import AgentState

from .conditional_logic import ConditionalLogic
from .node_names import ANALYST_NODE_NAMES, NodeNames


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
        workflow.add_node(NodeNames.BULL_RESEARCHER, create_bull_researcher(self.quick_thinking_llm))
        workflow.add_node(NodeNames.BEAR_RESEARCHER, create_bear_researcher(self.quick_thinking_llm))
        workflow.add_node(NodeNames.RESEARCH_MANAGER, create_research_manager(self.deep_thinking_llm))
        workflow.add_node(NodeNames.TRADER, create_trader(self.quick_thinking_llm))

        # Add risk analysis nodes.
        workflow.add_node(NodeNames.AGGRESSIVE_ANALYST, create_aggressive_debator(self.quick_thinking_llm))
        workflow.add_node(NodeNames.NEUTRAL_ANALYST, create_neutral_debator(self.quick_thinking_llm))
        workflow.add_node(NodeNames.CONSERVATIVE_ANALYST, create_conservative_debator(self.quick_thinking_llm))
        workflow.add_node(NodeNames.PORTFOLIO_MANAGER, create_portfolio_manager(self.deep_thinking_llm))

        # Fan-out: START → all analysts in parallel.
        for key in selected_analysts:
            workflow.add_edge(START, ANALYST_NODE_NAMES[key])

        # Fan-in: each analyst → Bull Researcher.
        # LangGraph will not advance to Bull Researcher until every incoming
        # edge (i.e. every analyst) has completed.
        for key in selected_analysts:
            workflow.add_edge(ANALYST_NODE_NAMES[key], NodeNames.BULL_RESEARCHER)

        # Research debate loop.
        workflow.add_conditional_edges(
            NodeNames.BULL_RESEARCHER,
            self.conditional_logic.should_continue_debate,
            {
                NodeNames.BEAR_RESEARCHER: NodeNames.BEAR_RESEARCHER,
                NodeNames.RESEARCH_MANAGER: NodeNames.RESEARCH_MANAGER,
            },
        )
        workflow.add_conditional_edges(
            NodeNames.BEAR_RESEARCHER,
            self.conditional_logic.should_continue_debate,
            {
                NodeNames.BULL_RESEARCHER: NodeNames.BULL_RESEARCHER,
                NodeNames.RESEARCH_MANAGER: NodeNames.RESEARCH_MANAGER,
            },
        )

        workflow.add_edge(NodeNames.RESEARCH_MANAGER, NodeNames.TRADER)
        workflow.add_edge(NodeNames.TRADER, NodeNames.AGGRESSIVE_ANALYST)

        # Risk debate loop.
        workflow.add_conditional_edges(
            NodeNames.AGGRESSIVE_ANALYST,
            self.conditional_logic.should_continue_risk_analysis,
            {
                NodeNames.CONSERVATIVE_ANALYST: NodeNames.CONSERVATIVE_ANALYST,
                NodeNames.PORTFOLIO_MANAGER: NodeNames.PORTFOLIO_MANAGER,
            },
        )
        workflow.add_conditional_edges(
            NodeNames.CONSERVATIVE_ANALYST,
            self.conditional_logic.should_continue_risk_analysis,
            {
                NodeNames.NEUTRAL_ANALYST: NodeNames.NEUTRAL_ANALYST,
                NodeNames.PORTFOLIO_MANAGER: NodeNames.PORTFOLIO_MANAGER,
            },
        )
        workflow.add_conditional_edges(
            NodeNames.NEUTRAL_ANALYST,
            self.conditional_logic.should_continue_risk_analysis,
            {
                NodeNames.AGGRESSIVE_ANALYST: NodeNames.AGGRESSIVE_ANALYST,
                NodeNames.PORTFOLIO_MANAGER: NodeNames.PORTFOLIO_MANAGER,
            },
        )

        workflow.add_edge(NodeNames.PORTFOLIO_MANAGER, END)

        return workflow
