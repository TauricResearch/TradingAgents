# TradingAgents/graph/setup.py

from typing import Any, Dict
from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from tradingagents.agents import *
from tradingagents.agents.utils.agent_states import AgentState

from .conditional_logic import ConditionalLogic


class GraphSetup:
    """Handles the setup and configuration of the agent graph."""

    def __init__(
        self,
        quick_thinking_llm: Any,
        deep_thinking_llm: Any,
        tool_nodes: Dict[str, ToolNode],
        conditional_logic: ConditionalLogic,
    ):
        """Initialize with required components."""
        self.quick_thinking_llm = quick_thinking_llm
        self.deep_thinking_llm = deep_thinking_llm
        self.tool_nodes = tool_nodes
        self.conditional_logic = conditional_logic

    def setup_graph(
        self,
        selected_analysts=["market", "social", "news", "fundamentals"],
        standalone=False,
    ):
        """Set up and compile the agent workflow graph.

        Args:
            selected_analysts (list): List of analyst types to include. Options are:
                - "market": Market analyst
                - "social": Social media analyst
                - "news": News analyst
                - "fundamentals": Fundamentals analyst
            standalone (bool): If True, stop after the analyst phase.
        """
        if len(selected_analysts) == 0:
            raise ValueError("Trading Agents Graph Setup Error: no analysts selected!")

        # Create analyst nodes
        analyst_nodes = {}
        delete_nodes = {}
        tool_nodes = {}

        if "market" in selected_analysts:
            analyst_nodes["market"] = create_market_analyst(self.quick_thinking_llm)
            delete_nodes["market"] = create_msg_delete("market_messages")
            tool_nodes["market"] = self.tool_nodes["market"]

        if "social" in selected_analysts:
            analyst_nodes["social"] = create_sentiment_analyst(self.quick_thinking_llm)
            delete_nodes["social"] = create_msg_delete("sentiment_messages")
            tool_nodes["social"] = self.tool_nodes["social"]

        if "news" in selected_analysts:
            analyst_nodes["news"] = create_news_analyst(self.quick_thinking_llm)
            delete_nodes["news"] = create_msg_delete("news_messages")
            tool_nodes["news"] = self.tool_nodes["news"]

        if "fundamentals" in selected_analysts:
            analyst_nodes["fundamentals"] = create_fundamentals_analyst(
                self.quick_thinking_llm
            )
            delete_nodes["fundamentals"] = create_msg_delete("fundamentals_messages")
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

        # Create workflow
        workflow = StateGraph(AgentState)

        # Add analyst nodes to the graph
        for analyst_type, node in analyst_nodes.items():
            workflow.add_node(f"{analyst_type.capitalize()} Analyst", node)
            workflow.add_node(
                f"Msg Clear {analyst_type.capitalize()}", delete_nodes[analyst_type]
            )
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
        
        def sync_analysts(state: AgentState):
            """Merge parallel analyst reports into the main message history.
            
            Reports are truncated to 4k characters each to prevent researchers 
            from being overwhelmed by excessive context.
            """
            # Gate: Only merge when all analysts have finished.
            if state["analyst_count"] < len(selected_analysts):
                return {}

            reports = []
            max_report_len = 4000
            
            def truncate(text):
                if not text: return ""
                if len(text) <= max_report_len: return text
                return text[:max_report_len] + "\n... (truncated for brevity) ..."

            if state.get("market_report"):
                reports.append(f"## Market Analysis\n{truncate(state['market_report'])}")
            if state.get("sentiment_report"):
                reports.append(f"## Sentiment Analysis\n{truncate(state['sentiment_report'])}")
            if state.get("news_report"):
                reports.append(f"## News Analysis\n{truncate(state['news_report'])}")
            if state.get("fundamentals_report"):
                reports.append(f"## Fundamentals Analysis\n{truncate(state['fundamentals_report'])}")
            
            if not reports:
                return {}
                
            combined_reports = "\n\n".join(reports)
            return {
                "messages": [HumanMessage(content=f"Here are the completed analyst reports:\n\n{combined_reports}")]
            }

        workflow.add_node("Analyst Synchronizer", sync_analysts)

        # Define edges
        # Start all selected analysts directly in parallel
        for analyst_type in selected_analysts:
            workflow.add_edge(START, f"{analyst_type.capitalize()} Analyst")

        # Connect each analyst to their tools and then to the synchronizer
        for analyst_type in selected_analysts:
            current_analyst = f"{analyst_type.capitalize()} Analyst"
            current_tools = f"tools_{analyst_type}"

            # Add conditional edges for current analyst
            workflow.add_conditional_edges(
                current_analyst,
                getattr(self.conditional_logic, f"should_continue_{analyst_type}"),
                {
                    f"tools_{analyst_type}": f"tools_{analyst_type}",
                    f"Msg Clear {analyst_type.capitalize()}": "Analyst Synchronizer" # Analysts now self-clean, but we route to Synchronizer
                },
            )
            workflow.add_edge(current_tools, current_analyst)

        def should_proceed_from_sync(state: AgentState):
            if state["analyst_count"] >= len(selected_analysts):
                return "proceed"
            return "wait"

        # Route from synchronizer: only proceed on the FINAL parallel update.
        workflow.add_conditional_edges(
            "Analyst Synchronizer",
            should_proceed_from_sync,
            {
                "proceed": END if standalone else "Bull Researcher",
                "wait": END
            }
        )

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
