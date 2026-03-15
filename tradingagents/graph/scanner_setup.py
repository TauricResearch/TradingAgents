# tradingagents/graph/scanner_setup.py
from typing import Dict, Any
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode

from tradingagents.agents.utils.scanner_tools import (
    get_market_movers,
    get_market_indices,
    get_sector_performance,
    get_industry_performance,
    get_topic_news,
)

from .conditional_logic import ConditionalLogic


def pass_through_node(state):
    """Pass-through node that returns state unchanged."""
    return state


class ScannerGraphSetup:
    """Handles the setup and configuration of the scanner graph."""

    def __init__(self, conditional_logic: ConditionalLogic):
        self.conditional_logic = conditional_logic

    def setup_graph(self):
        """Set up and compile the scanner workflow graph."""
        workflow = StateGraph(dict)

        # Add tool nodes
        tool_nodes = {
            "get_market_movers": ToolNode([get_market_movers]),
            "get_market_indices": ToolNode([get_market_indices]),
            "get_sector_performance": ToolNode([get_sector_performance]),
            "get_industry_performance": ToolNode([get_industry_performance]),
            "get_topic_news": ToolNode([get_topic_news]),
        }

        for name, node in tool_nodes.items():
            workflow.add_node(name, node)

        # Add conditional logic node
        workflow.add_node("conditional_logic", self.conditional_logic)
        
        # Add pass-through nodes for industry deep dive and macro synthesis
        workflow.add_node("industry_deep_dive", pass_through_node)
        workflow.add_node("macro_synthesis", pass_through_node)
        
        # Fan-out from START to 3 scanners
        workflow.add_edge(START, "get_market_movers")
        workflow.add_edge(START, "get_sector_performance")
        workflow.add_edge(START, "get_topic_news")

        # Fan-in to industry deep dive
        workflow.add_edge("get_market_movers", "industry_deep_dive")
        workflow.add_edge("get_sector_performance", "industry_deep_dive")
        workflow.add_edge("get_topic_news", "industry_deep_dive")

        # Then to synthesis
        workflow.add_edge("industry_deep_dive", "macro_synthesis")
        workflow.add_edge("macro_synthesis", END)
        
        return workflow.compile()