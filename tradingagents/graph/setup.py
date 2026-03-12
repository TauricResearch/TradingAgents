# TradingAgents/graph/setup.py

from typing import Dict
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph, START
from langgraph.prebuilt import ToolNode

from tradingagents.agents import (
    create_market_analyst,
    create_news_analyst,
    create_fundamentals_analyst,
    create_msg_delete,
    create_trader,
)
from tradingagents.agents.utils.agent_states import AgentState

from .conditional_logic import ConditionalLogic


class GraphSetup:
    """Handles the setup and configuration of the swing trading graph.

    Simplified flow: Analysts → Trader → END
    No debate or risk management nodes.
    """

    def __init__(
        self,
        quick_thinking_llm: ChatOpenAI,
        deep_thinking_llm: ChatOpenAI,
        tool_nodes: Dict[str, ToolNode],
        trader_memory,
        conditional_logic: ConditionalLogic,
    ):
        self.quick_thinking_llm = quick_thinking_llm
        self.deep_thinking_llm = deep_thinking_llm
        self.tool_nodes = tool_nodes
        self.trader_memory = trader_memory
        self.conditional_logic = conditional_logic

    def setup_graph(
        self, selected_analysts=["market", "news", "fundamentals"]
    ):
        """Set up the swing trading workflow graph.

        Args:
            selected_analysts: List of analyst types to include.
                Options: "market", "news", "fundamentals"
        """
        if len(selected_analysts) == 0:
            raise ValueError("Trading Agents Graph Setup Error: no analysts selected!")

        # Create analyst nodes
        analyst_creators = {
            "market": create_market_analyst,
            "news": create_news_analyst,
            "fundamentals": create_fundamentals_analyst,
        }

        analyst_nodes = {}
        delete_nodes = {}
        tool_nodes = {}

        for analyst_type in selected_analysts:
            if analyst_type not in analyst_creators:
                continue
            analyst_nodes[analyst_type] = analyst_creators[analyst_type](
                self.quick_thinking_llm
            )
            delete_nodes[analyst_type] = create_msg_delete()
            tool_nodes[analyst_type] = self.tool_nodes[analyst_type]

        # Create trader node
        trader_node = create_trader(self.deep_thinking_llm, self.trader_memory)

        # Build workflow
        workflow = StateGraph(AgentState)

        # Add analyst nodes
        for analyst_type, node in analyst_nodes.items():
            workflow.add_node(f"{analyst_type.capitalize()} Analyst", node)
            workflow.add_node(
                f"Msg Clear {analyst_type.capitalize()}", delete_nodes[analyst_type]
            )
            workflow.add_node(f"tools_{analyst_type}", tool_nodes[analyst_type])

        # Add trader node
        workflow.add_node("Trader", trader_node)

        # Wire edges: START → first analyst
        active_analysts = [a for a in selected_analysts if a in analyst_nodes]
        first_analyst = active_analysts[0]
        workflow.add_edge(START, f"{first_analyst.capitalize()} Analyst")

        # Connect analysts in sequence
        for i, analyst_type in enumerate(active_analysts):
            current_analyst = f"{analyst_type.capitalize()} Analyst"
            current_tools = f"tools_{analyst_type}"
            current_clear = f"Msg Clear {analyst_type.capitalize()}"

            # Tool call loop
            workflow.add_conditional_edges(
                current_analyst,
                getattr(self.conditional_logic, f"should_continue_{analyst_type}"),
                [current_tools, current_clear],
            )
            workflow.add_edge(current_tools, current_analyst)

            # Connect to next analyst or to Trader
            if i < len(active_analysts) - 1:
                next_analyst = f"{active_analysts[i + 1].capitalize()} Analyst"
                workflow.add_edge(current_clear, next_analyst)
            else:
                workflow.add_edge(current_clear, "Trader")

        # Trader → END
        workflow.add_edge("Trader", END)

        return workflow.compile()
