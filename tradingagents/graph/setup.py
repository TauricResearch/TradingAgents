# TradingAgents/graph/setup.py

from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from tradingagents.agents import (
    create_aggressive_debator,
    create_bear_researcher,
    create_bull_researcher,
    create_conservative_debator,
    create_evidence_steward,
    create_fundamentals_analyst,
    create_market_analyst,
    create_msg_delete,
    create_neutral_debator,
    create_news_analyst,
    create_portfolio_manager,
    create_research_manager,
    create_sentiment_analyst,
    create_trader,
)
from tradingagents.agents.utils.agent_states import AgentState
from tradingagents.observability.roles import ROLES_BY_NODE_ID

from .analyst_execution import build_analyst_execution_plan
from .conditional_logic import ConditionalLogic

# Every target a shared conditional router can return. Each edge driven by the
# router maps all of them, so a fall-through return (e.g. under prompt/i18n/
# refactor drift in the speaker labels) can never hit a missing path_map entry
# and crash LangGraph mid-run (#1088).
DEBATE_PATH_MAP = {
    "Bull Researcher": "Bull Researcher",
    "Bear Researcher": "Bear Researcher",
    "Research Manager": "Research Manager",
}
RISK_ANALYSIS_PATH_MAP = {
    "Aggressive Analyst": "Aggressive Analyst",
    "Conservative Analyst": "Conservative Analyst",
    "Neutral Analyst": "Neutral Analyst",
    "Portfolio Manager": "Portfolio Manager",
}


class GraphSetup:
    """Handles the setup and configuration of the agent graph."""

    def __init__(
        self,
        quick_thinking_llm: Any,
        deep_thinking_llm: Any,
        tool_nodes: dict[str, ToolNode],
        conditional_logic: ConditionalLogic,
    ):
        """Initialize with required components."""
        self.quick_thinking_llm = quick_thinking_llm
        self.deep_thinking_llm = deep_thinking_llm
        self.tool_nodes = tool_nodes
        self.conditional_logic = conditional_logic

    def setup_graph(
        self,
        selected_analysts=("market", "social", "news", "fundamentals"),
        *,
        observation_enabled: bool = False,
    ):
        """Set up and compile the agent workflow graph.

        Args:
            selected_analysts (list): List of analyst types to include. Options are:
                - "market": Market analyst
                - "social": Social media analyst
                - "news": News analyst
                - "fundamentals": Fundamentals analyst
        """
        plan = build_analyst_execution_plan(selected_analysts)

        analyst_factories = {
            "market": lambda: create_market_analyst(self.quick_thinking_llm),
            "social": lambda: create_sentiment_analyst(self.quick_thinking_llm),
            "news": lambda: create_news_analyst(self.quick_thinking_llm),
            "fundamentals": lambda: create_fundamentals_analyst(self.quick_thinking_llm),
        }

        # Create Evidence Steward gate node (fork-specific: evidence quality check)
        evidence_steward_node = create_evidence_steward()

        # Create researcher and manager nodes
        bull_researcher_node = create_bull_researcher(self.quick_thinking_llm)
        bear_researcher_node = create_bear_researcher(self.quick_thinking_llm)
        research_manager_node = create_research_manager(self.deep_thinking_llm)
        trader_node = create_trader(self.quick_thinking_llm)

        # Create risk analysis nodes
        aggressive_analyst = create_aggressive_debator(self.quick_thinking_llm)
        neutral_analyst = create_neutral_debator(self.quick_thinking_llm)
        conservative_analyst = create_conservative_debator(self.quick_thinking_llm)
        portfolio_manager_node = create_portfolio_manager(self.deep_thinking_llm)

        # Create workflow
        if observation_enabled:
            from tradingagents.observability.graph_tasks import (
                GraphObservationRunContext,
                ObservedGraphTask,
                ObservedNode,
                ObservedToolNode,
            )

            context_schema = GraphObservationRunContext
        else:
            ObservedGraphTask = ObservedNode = ObservedToolNode = None
            context_schema = None

        workflow = StateGraph(AgentState, context_schema=context_schema)

        def role_node(node_name: str, node: Any):
            if not observation_enabled:
                return node
            assert ObservedNode is not None
            return ObservedNode(ROLES_BY_NODE_ID[node_name].actor_id, node_name, node)

        # Add analyst nodes to the graph
        for spec in plan.specs:
            workflow.add_node(
                spec.agent_node,
                role_node(spec.agent_node, analyst_factories[spec.key]()),
            )
            clear_node = create_msg_delete()
            tool_node = self.tool_nodes[spec.key]
            if observation_enabled:
                assert ObservedGraphTask is not None and ObservedToolNode is not None
                clear_node = ObservedGraphTask(spec.clear_node, "maintenance", clear_node)
                tool_node = ObservedToolNode(spec.tool_node, tool_node)
            workflow.add_node(spec.clear_node, clear_node)
            workflow.add_node(spec.tool_node, tool_node)

        # Add other nodes
        workflow.add_node(
            "Evidence Steward", role_node("Evidence Steward", evidence_steward_node)
        )
        workflow.add_node("Bull Researcher", role_node("Bull Researcher", bull_researcher_node))
        workflow.add_node("Bear Researcher", role_node("Bear Researcher", bear_researcher_node))
        workflow.add_node(
            "Research Manager", role_node("Research Manager", research_manager_node)
        )
        workflow.add_node("Trader", role_node("Trader", trader_node))
        workflow.add_node(
            "Aggressive Analyst", role_node("Aggressive Analyst", aggressive_analyst)
        )
        workflow.add_node("Neutral Analyst", role_node("Neutral Analyst", neutral_analyst))
        workflow.add_node(
            "Conservative Analyst", role_node("Conservative Analyst", conservative_analyst)
        )
        workflow.add_node(
            "Portfolio Manager", role_node("Portfolio Manager", portfolio_manager_node)
        )

        # Define edges
        # Start with the first analyst
        workflow.add_edge(START, plan.specs[0].agent_node)

        # Connect analysts in sequence
        for i, spec in enumerate(plan.specs):
            current_analyst = spec.agent_node
            current_tools = spec.tool_node
            current_clear = spec.clear_node

            # Add conditional edges for current analyst
            workflow.add_conditional_edges(
                current_analyst,
                getattr(self.conditional_logic, f"should_continue_{spec.key}"),
                [current_tools, current_clear],
            )
            workflow.add_edge(current_tools, current_analyst)

            # Connect to next analyst or to Evidence Steward if this is the last analyst
            if i < len(plan.specs) - 1:
                workflow.add_edge(current_clear, plan.specs[i + 1].agent_node)
            else:
                workflow.add_edge(current_clear, "Evidence Steward")

        workflow.add_edge("Evidence Steward", "Bull Researcher")

        # Both research-debate edges share the complete DEBATE_PATH_MAP (#1088).
        for debate_node in ("Bull Researcher", "Bear Researcher"):
            workflow.add_conditional_edges(
                debate_node,
                self.conditional_logic.should_continue_debate,
                DEBATE_PATH_MAP,
            )
        workflow.add_edge("Research Manager", "Trader")
        workflow.add_edge("Trader", "Aggressive Analyst")
        # All three risk edges share the complete RISK_ANALYSIS_PATH_MAP (#1088).
        for risk_node in ("Aggressive Analyst", "Conservative Analyst", "Neutral Analyst"):
            workflow.add_conditional_edges(
                risk_node,
                self.conditional_logic.should_continue_risk_analysis,
                RISK_ANALYSIS_PATH_MAP,
            )

        workflow.add_edge("Portfolio Manager", END)

        return workflow
