from typing import Any, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed
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
        self.quick_thinking_llm = quick_thinking_llm
        self.deep_thinking_llm = deep_thinking_llm
        self.tool_nodes = tool_nodes
        self.conditional_logic = conditional_logic

    def _create_parallel_analyst_node(self, selected_analysts):
        factories = {
            "market": create_market_analyst,
            "social": create_social_media_analyst,
            "news": create_news_analyst,
            "fundamentals": create_fundamentals_analyst,
        }
        report_keys = {
            "market": "market_report",
            "social": "sentiment_report",
            "news": "news_report",
            "fundamentals": "fundamentals_report",
        }

        def parallel_analyst_node(state):
            max_tool_iterations = self.conditional_logic.max_debate_rounds * 5

            def run_single_analyst(analyst_type):
                node_fn = factories[analyst_type](self.quick_thinking_llm)
                tools_node = self.tool_nodes[analyst_type]
                local_messages = list(state["messages"])

                for _ in range(max_tool_iterations):
                    local_state = {**state, "messages": local_messages}
                    analyst_result = node_fn(local_state)
                    new_messages = analyst_result.get("messages", [])
                    local_messages.extend(new_messages)

                    last_msg = new_messages[-1] if new_messages else None
                    if not last_msg or not hasattr(last_msg, 'tool_calls') or not last_msg.tool_calls:
                        return analyst_type, analyst_result

                    tool_state = {"messages": [last_msg]}
                    tool_result = tools_node.invoke(tool_state)
                    local_messages.extend(tool_result["messages"])

                return analyst_type, analyst_result

            results = {}
            with ThreadPoolExecutor(max_workers=len(selected_analysts)) as executor:
                futures = {executor.submit(run_single_analyst, t): t for t in selected_analysts}
                for future in as_completed(futures):
                    analyst_type, analyst_result = future.result()
                    results[analyst_type] = analyst_result

            merged = {}
            for analyst_type, analyst_result in results.items():
                key = report_keys[analyst_type]
                merged[key] = analyst_result.get(key, "")

            return merged

        return parallel_analyst_node

    def setup_graph(
        self, selected_analysts=["market", "social", "news", "fundamentals"]
    ):
        if len(selected_analysts) == 0:
            raise ValueError("Trading Agents Graph Setup Error: no analysts selected!")

        bull_researcher_node = create_bull_researcher(self.quick_thinking_llm)
        bear_researcher_node = create_bear_researcher(self.quick_thinking_llm)
        research_manager_node = create_research_manager(self.deep_thinking_llm)
        trader_node = create_trader(self.quick_thinking_llm)

        aggressive_analyst = create_aggressive_debator(self.quick_thinking_llm)
        neutral_analyst = create_neutral_debator(self.quick_thinking_llm)
        conservative_analyst = create_conservative_debator(self.quick_thinking_llm)
        portfolio_manager_node = create_portfolio_manager(self.deep_thinking_llm)

        parallel_analyst_node = self._create_parallel_analyst_node(selected_analysts)

        workflow = StateGraph(AgentState)

        workflow.add_node("Analyst Team", parallel_analyst_node)

        workflow.add_node("Bull Researcher", bull_researcher_node)
        workflow.add_node("Bear Researcher", bear_researcher_node)
        workflow.add_node("Research Manager", research_manager_node)
        workflow.add_node("Trader", trader_node)
        workflow.add_node("Aggressive Analyst", aggressive_analyst)
        workflow.add_node("Neutral Analyst", neutral_analyst)
        workflow.add_node("Conservative Analyst", conservative_analyst)
        workflow.add_node("Portfolio Manager", portfolio_manager_node)

        workflow.add_edge(START, "Analyst Team")
        workflow.add_edge("Analyst Team", "Bull Researcher")

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
