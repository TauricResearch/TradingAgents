# TradingAgents/graph/setup.py

import concurrent.futures
import time
from typing import Any, Dict
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
        bull_memory,
        bear_memory,
        trader_memory,
        invest_judge_memory,
        portfolio_manager_memory,
        conditional_logic: ConditionalLogic,
        research_node_timeout_secs: float = 30.0,
    ):
        """Initialize with required components."""
        self.quick_thinking_llm = quick_thinking_llm
        self.deep_thinking_llm = deep_thinking_llm
        self.tool_nodes = tool_nodes
        self.bull_memory = bull_memory
        self.bear_memory = bear_memory
        self.trader_memory = trader_memory
        self.invest_judge_memory = invest_judge_memory
        self.portfolio_manager_memory = portfolio_manager_memory
        self.conditional_logic = conditional_logic
        self.research_node_timeout_secs = research_node_timeout_secs

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
        if len(selected_analysts) == 0:
            raise ValueError("Trading Agents Graph Setup Error: no analysts selected!")

        # Create analyst nodes
        analyst_nodes = {}
        delete_nodes = {}
        tool_nodes = {}

        if "market" in selected_analysts:
            analyst_nodes["market"] = create_market_analyst(
                self.quick_thinking_llm
            )
            delete_nodes["market"] = create_msg_delete()
            tool_nodes["market"] = self.tool_nodes["market"]

        if "social" in selected_analysts:
            analyst_nodes["social"] = create_social_media_analyst(
                self.quick_thinking_llm
            )
            delete_nodes["social"] = create_msg_delete()
            tool_nodes["social"] = self.tool_nodes["social"]

        if "news" in selected_analysts:
            analyst_nodes["news"] = create_news_analyst(
                self.quick_thinking_llm
            )
            delete_nodes["news"] = create_msg_delete()
            tool_nodes["news"] = self.tool_nodes["news"]

        if "fundamentals" in selected_analysts:
            analyst_nodes["fundamentals"] = create_fundamentals_analyst(
                self.quick_thinking_llm
            )
            delete_nodes["fundamentals"] = create_msg_delete()
            tool_nodes["fundamentals"] = self.tool_nodes["fundamentals"]

        # Create researcher and manager nodes
        bull_researcher_node = self._guard_research_node(
            "Bull Researcher",
            self.quick_thinking_llm, self.bull_memory
        )
        bear_researcher_node = self._guard_research_node(
            "Bear Researcher",
            self.quick_thinking_llm, self.bear_memory
        )
        research_manager_node = self._guard_research_node(
            "Research Manager",
            self.deep_thinking_llm, self.invest_judge_memory
        )
        trader_node = create_trader(self.quick_thinking_llm, self.trader_memory)

        # Create risk analysis nodes
        aggressive_analyst = create_aggressive_debator(self.quick_thinking_llm)
        neutral_analyst = create_neutral_debator(self.quick_thinking_llm)
        conservative_analyst = create_conservative_debator(self.quick_thinking_llm)
        portfolio_manager_node = create_portfolio_manager(
            self.deep_thinking_llm, self.portfolio_manager_memory
        )

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

        # Define edges
        # Start with the first analyst
        first_analyst = selected_analysts[0]
        workflow.add_edge(START, f"{first_analyst.capitalize()} Analyst")

        # Connect analysts in sequence
        for i, analyst_type in enumerate(selected_analysts):
            current_analyst = f"{analyst_type.capitalize()} Analyst"
            current_tools = f"tools_{analyst_type}"
            current_clear = f"Msg Clear {analyst_type.capitalize()}"

            # Add conditional edges for current analyst
            workflow.add_conditional_edges(
                current_analyst,
                getattr(self.conditional_logic, f"should_continue_{analyst_type}"),
                [current_tools, current_clear],
            )
            workflow.add_edge(current_tools, current_analyst)

            # Connect to next analyst or to Bull Researcher if this is the last analyst
            if i < len(selected_analysts) - 1:
                next_analyst = f"{selected_analysts[i+1].capitalize()} Analyst"
                workflow.add_edge(current_clear, next_analyst)
            else:
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

        # Compile and return
        return workflow.compile()

    def _guard_research_node(self, node_name: str, llm: Any, memory):
        if node_name == "Bull Researcher":
            node = create_bull_researcher(llm, memory)
            dimension = "bull"
        elif node_name == "Bear Researcher":
            node = create_bear_researcher(llm, memory)
            dimension = "bear"
        else:
            node = create_research_manager(llm, memory)
            dimension = "manager"

        def wrapped(state):
            started_at = time.time()
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            future = executor.submit(node, state)
            try:
                result = future.result(timeout=self.research_node_timeout_secs)
                return self._apply_research_success(state, result, dimension)
            except concurrent.futures.TimeoutError:
                future.cancel()
                executor.shutdown(wait=False, cancel_futures=True)
                return self._apply_research_fallback(
                    state,
                    node_name=node_name,
                    dimension=dimension,
                    reason=f"{node_name.lower().replace(' ', '_')}_timeout",
                    started_at=started_at,
                )
            except Exception as exc:
                executor.shutdown(wait=False, cancel_futures=True)
                return self._apply_research_fallback(
                    state,
                    node_name=node_name,
                    dimension=dimension,
                    reason=f"{node_name.lower().replace(' ', '_')}_{type(exc).__name__.lower()}",
                    started_at=started_at,
                )
            finally:
                executor.shutdown(wait=False, cancel_futures=True)

        return wrapped

    @staticmethod
    def _provenance(state) -> dict:
        debate_state = dict(state["investment_debate_state"])
        return {
            "research_status": debate_state.get("research_status", "full"),
            "research_mode": debate_state.get("research_mode", "debate"),
            "timed_out_nodes": list(debate_state.get("timed_out_nodes", [])),
            "degraded_reason": debate_state.get("degraded_reason"),
            "covered_dimensions": list(debate_state.get("covered_dimensions", [])),
            "manager_confidence": debate_state.get("manager_confidence"),
        }

    def _apply_research_success(self, state, result: dict, dimension: str):
        debate_state = dict(result.get("investment_debate_state") or state["investment_debate_state"])
        provenance = self._provenance(state)
        if dimension not in provenance["covered_dimensions"]:
            provenance["covered_dimensions"].append(dimension)
        if provenance["research_status"] == "full":
            provenance["research_mode"] = "debate"
        if dimension == "manager" and provenance["manager_confidence"] is None:
            provenance["manager_confidence"] = 1.0 if provenance["research_status"] == "full" else 0.5
        debate_state.update(provenance)
        updated = dict(result)
        updated["investment_debate_state"] = debate_state
        return updated

    def _apply_research_fallback(self, state, *, node_name: str, dimension: str, reason: str, started_at: float):
        debate_state = dict(state["investment_debate_state"])
        provenance = self._provenance(state)
        provenance["research_status"] = "degraded"
        provenance["research_mode"] = "degraded_synthesis"
        provenance["degraded_reason"] = reason
        if "timeout" in reason and node_name not in provenance["timed_out_nodes"]:
            provenance["timed_out_nodes"].append(node_name)

        elapsed_seconds = round(time.time() - started_at, 3)
        if dimension == "manager":
            provenance["manager_confidence"] = 0.0
            fallback = (
                "Recommendation: HOLD\n"
                f"Top reasons: research degraded at {node_name} ({reason}); use partial research context cautiously.\n"
                f"Simple execution plan: keep sizing conservative and wait for confirmation. Guard elapsed={elapsed_seconds}s."
            )
            debate_state["judge_decision"] = fallback
            debate_state["current_response"] = fallback
            debate_state.update(provenance)
            return {
                "investment_debate_state": debate_state,
                "investment_plan": fallback,
            }

        prefix = "Bull Analyst" if dimension == "bull" else "Bear Analyst"
        history_field = "bull_history" if dimension == "bull" else "bear_history"
        degraded_argument = (
            f"{prefix}: [DEGRADED] {node_name} unavailable ({reason}). "
            f"Proceeding with partial research context. Guard elapsed={elapsed_seconds}s."
        )
        debate_state["history"] = debate_state.get("history", "") + "\n" + degraded_argument
        debate_state[history_field] = debate_state.get(history_field, "") + "\n" + degraded_argument
        debate_state["current_response"] = degraded_argument
        debate_state["count"] = debate_state.get("count", 0) + 1
        debate_state.update(provenance)
        return {"investment_debate_state": debate_state}
