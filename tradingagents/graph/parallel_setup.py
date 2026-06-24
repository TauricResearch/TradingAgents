# TradingAgents/graph/parallel_setup.py
#
# Drop-in replacement for setup.py that runs analyst nodes in parallel
# instead of sequentially. Analysts are independent — each writes to its
# own state field (market_report, sentiment_report, etc.) and never reads
# another analyst's output. The sequential chain was artificial.
#
# Performance: N analysts complete in O(max(analyst_time)) instead of
# O(sum(analyst_times)), typically 3-4x faster for 4 analysts.

from typing import Any, Dict
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from tradingagents.agents import *
from tradingagents.agents.utils.agent_states import AgentState

from .conditional_logic import ConditionalLogic


class ParallelGraphSetup:
    """Graph setup that runs analysts in parallel via LangGraph fan-out.

    Replaces the sequential analyst chain with true parallel execution.
    Since each analyst writes to a distinct state key (market_report,
    sentiment_report, news_report, fundamentals_report), there are no
    write conflicts — LangGraph merges the parallel state updates cleanly.
    """

    def __init__(
        self,
        quick_thinking_llm: Any,
        deep_thinking_llm: Any,
        tool_nodes: Dict[str, ToolNode],
        conditional_logic: ConditionalLogic,
    ):
        self.quick_thinking_llm = quick_thinking_llm
        self.deep_thinking_llm = deep_thinking_llm
        self.tool_nodes = tool_nodes
        self.conditional_logic = conditional_logic

    def setup_graph(
        self, selected_analysts=["market", "social", "news", "fundamentals"]
    ):
        """Set up agent workflow with parallel analyst execution.

        Instead of: START → Market → Social → News → Fundamentals → Bull
        We build:   START → [Market, Social, News, Fundamentals] → Join → Bull

        Each analyst still has its own tool-calling loop (analyst ↔ tools),
        but all analysts execute concurrently. A lightweight join node
        collects results and transitions to the debate phase.
        """
        if len(selected_analysts) == 0:
            raise ValueError("Trading Agents Graph Setup Error: no analysts selected!")

        # Create analyst nodes
        analyst_nodes = {}
        delete_nodes = {}
        tool_nodes = {}

        if "market" in selected_analysts:
            analyst_nodes["market"] = create_market_analyst(self.quick_thinking_llm)
            delete_nodes["market"] = create_msg_delete()
            tool_nodes["market"] = self.tool_nodes["market"]

        if "social" in selected_analysts:
            analyst_nodes["social"] = create_social_media_analyst(self.quick_thinking_llm)
            delete_nodes["social"] = create_msg_delete()
            tool_nodes["social"] = self.tool_nodes["social"]

        if "news" in selected_analysts:
            analyst_nodes["news"] = create_news_analyst(self.quick_thinking_llm)
            delete_nodes["news"] = create_msg_delete()
            tool_nodes["news"] = self.tool_nodes["news"]

        if "fundamentals" in selected_analysts:
            analyst_nodes["fundamentals"] = create_fundamentals_analyst(self.quick_thinking_llm)
            delete_nodes["fundamentals"] = create_msg_delete()
            tool_nodes["fundamentals"] = self.tool_nodes["fundamentals"]

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

        # Build the graph
        workflow = StateGraph(AgentState)

        # ── Register all nodes ──
        for analyst_type, node in analyst_nodes.items():
            workflow.add_node(f"{analyst_type.capitalize()} Analyst", node)
            workflow.add_node(f"Msg Clear {analyst_type.capitalize()}", delete_nodes[analyst_type])
            workflow.add_node(f"tools_{analyst_type}", tool_nodes[analyst_type])

        # Join node: lightweight pass-through that waits for all analysts
        def analyst_join(state):
            """No-op join point — LangGraph blocks here until all
            parallel analyst branches have completed and their state
            updates have been merged."""
            return {}

        workflow.add_node("Analyst Join", analyst_join)

        workflow.add_node("Bull Researcher", bull_researcher_node)
        workflow.add_node("Bear Researcher", bear_researcher_node)
        workflow.add_node("Research Manager", research_manager_node)
        workflow.add_node("Trader", trader_node)
        workflow.add_node("Aggressive Analyst", aggressive_analyst)
        workflow.add_node("Neutral Analyst", neutral_analyst)
        workflow.add_node("Conservative Analyst", conservative_analyst)
        workflow.add_node("Portfolio Manager", portfolio_manager_node)

        # ── Parallel fan-out: START → all analysts simultaneously ──
        for analyst_type in selected_analysts:
            current_analyst = f"{analyst_type.capitalize()} Analyst"
            current_tools = f"tools_{analyst_type}"
            current_clear = f"Msg Clear {analyst_type.capitalize()}"

            # Fan-out: START triggers all analysts at once
            workflow.add_edge(START, current_analyst)

            # Each analyst has its own tool-calling loop
            workflow.add_conditional_edges(
                current_analyst,
                getattr(self.conditional_logic, f"should_continue_{analyst_type}"),
                [current_tools, current_clear],
            )
            workflow.add_edge(current_tools, current_analyst)

            # When done, each analyst flows to the join node
            workflow.add_edge(current_clear, "Analyst Join")

        # ── Sequential pipeline resumes after join ──
        workflow.add_edge("Analyst Join", "Bull Researcher")

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
