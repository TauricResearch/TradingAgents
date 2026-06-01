# TradingAgents/graph/setup.py

from typing import Any, Dict
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from tradingagents.agents import (
    AgentState,
    InvestDebateState,
    RiskDebateState,
    create_msg_delete,
    create_bear_researcher,
    create_bull_researcher,
    create_aggressive_debator,
    create_conservative_debator,
    create_neutral_debator,
    create_research_manager,
    create_portfolio_manager,
    create_trader,
)
# Import all analyst modules so their @register_analyst decorators fire and
# populate the registry before setup_graph() queries it.
import tradingagents.agents.analysts.market_analyst        # noqa: F401
import tradingagents.agents.analysts.sentiment_analyst      # noqa: F401
import tradingagents.agents.analysts.news_analyst           # noqa: F401
import tradingagents.agents.analysts.fundamentals_analyst   # noqa: F401
import tradingagents.agents.analysts.macro_analyst          # noqa: F401
import tradingagents.agents.analysts.options_analyst        # noqa: F401
import tradingagents.agents.analysts.quant_analyst          # noqa: F401
import tradingagents.agents.analysts.earnings_analyst       # noqa: F401
import tradingagents.agents.analysts.review_analyst         # noqa: F401

from tradingagents.agents.analyst_registry import get_factory, sync_registry_to_graph
from .analyst_execution import build_analyst_execution_plan
from .conditional_logic import ConditionalLogic


class GraphSetup:
    """Handles the setup and configuration of the agent graph."""

    def __init__(
        self,
        quick_thinking_llm: Any,
        deep_thinking_llm: Any,
        tool_nodes: Dict[str, ToolNode],
        conditional_logic: ConditionalLogic,
        analyst_concurrency_limit: int = 1,
    ):
        """Initialize with required components."""
        self.quick_thinking_llm = quick_thinking_llm
        self.deep_thinking_llm = deep_thinking_llm
        self.tool_nodes = tool_nodes
        self.conditional_logic = conditional_logic
        self.analyst_concurrency_limit = analyst_concurrency_limit

    def setup_graph(
        self, selected_analysts=["market", "social", "news", "fundamentals"]
    ):
        """Set up and compile the agent workflow graph.

        Args:
            selected_analysts (list): List of analyst types to include. Options are:
                - "market": Market analyst
                - "social": Social media analyst
                - "news": News analyst
                - "fundamentals": Fundamentals analyst
        """
        # Sync registry side-effects now that all packages are fully initialized.
        # This adds custom analysts to ANALYST_NODE_SPECS and injects their
        # should_continue_<key>() methods into ConditionalLogic.
        sync_registry_to_graph()

        plan = build_analyst_execution_plan(
            selected_analysts,
            concurrency_limit=self.analyst_concurrency_limit,
        )

        # Build analyst factory lambdas from the plugin registry.
        # Any custom analyst registered via @register_analyst is automatically
        # available here without modifying this file.
        analyst_factories = {
            spec.key: (
                lambda k=spec.key: get_factory(k)(self.quick_thinking_llm)
            )
            for spec in plan.specs
        }

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
        workflow = StateGraph(AgentState)

        # Add analyst nodes to the graph
        for spec in plan.specs:
            workflow.add_node(spec.agent_node, analyst_factories[spec.key]())
            workflow.add_node(spec.clear_node, create_msg_delete())
            workflow.add_node(spec.tool_node, self.tool_nodes[spec.key])

        # Add other nodes
        workflow.add_node("Bull Researcher", bull_researcher_node)
        workflow.add_node("Bear Researcher", bear_researcher_node)
        workflow.add_node("Research Manager", research_manager_node)
        workflow.add_node("Trader", trader_node)
        workflow.add_node("Aggressive Analyst", aggressive_analyst)
        workflow.add_node("Neutral Analyst", neutral_analyst)
        workflow.add_node("Conservative Analyst", conservative_analyst)
        workflow.add_node("Portfolio Manager", portfolio_manager_node)

        # Define edges based on concurrency limit
        if self.analyst_concurrency_limit == 1:
            # Sequential execution: chain analysts one after another
            for i, spec in enumerate(plan.specs):
                if i == 0:
                    workflow.add_edge(START, spec.agent_node)
                else:
                    prev_spec = plan.specs[i - 1]
                    workflow.add_edge(prev_spec.clear_node, spec.agent_node)

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

            # Direct the final analyst's clear node to the Bull Researcher fan-in point
            if plan.specs:
                workflow.add_edge(plan.specs[-1].clear_node, "Bull Researcher")
        else:
            # Parallel execution: start all selected analysts in parallel from START
            for spec in plan.specs:
                workflow.add_edge(START, spec.agent_node)

            # Connect each analyst to its tool node, and fan-in to Bull Researcher upon clearing
            for spec in plan.specs:
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

                # Direct to Bull Researcher fan-in point
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

        return workflow
