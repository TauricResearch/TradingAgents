# TradingAgents/graph/setup.py

from functools import wraps
from time import perf_counter
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
        trading_mode: str = "live",
        portfolio_state_policy_config: dict | None = None,
    ):
        """Initialize with required components.

        trading_mode selects which Portfolio Manager implementation is wired
        in: "backtest" uses the state-first agent (LLM emits MarketState,
        Python policy builds orders); anything else uses the legacy live
        portfolio manager.
        """
        self.quick_thinking_llm = quick_thinking_llm
        self.deep_thinking_llm = deep_thinking_llm
        self.tool_nodes = tool_nodes
        self.bull_memory = bull_memory
        self.bear_memory = bear_memory
        self.trader_memory = trader_memory
        self.invest_judge_memory = invest_judge_memory
        self.portfolio_manager_memory = portfolio_manager_memory
        self.conditional_logic = conditional_logic
        self.trading_mode = trading_mode
        self.portfolio_state_policy_config = portfolio_state_policy_config
    
    @staticmethod
    def _timed_agent_node(node_name: str, node):

        @wraps(node)
        def wrapped(state):
            ticker = state.get("company_of_interest", "?") if isinstance(state, dict) else "?"
            trade_date = state.get("trade_date", "?") if isinstance(state, dict) else "?"
            start = perf_counter()
            """
            print(
                f"[agent_timing] START node={node_name} ticker={ticker} trade_date={trade_date}",
                flush=True,
            )
            """
            try:
                result = node(state)
            except Exception:
                elapsed = perf_counter() - start
                """
                print(
                    f"[agent_timing] ERROR node={node_name} ticker={ticker} "
                    f"trade_date={trade_date} elapsed={elapsed:.3f}s",
                    flush=True,
                )
                """
                raise
            elapsed = perf_counter() - start
            """
            print(
                f"[agent_timing] END node={node_name} ticker={ticker} "
                f"trade_date={trade_date} elapsed={elapsed:.3f}s",
                flush=True,
            )
            """
            return result

        return wrapped
    

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
        force_finalize_nodes = {}

        analyst_report_keys = {
            "market": ("market_report", "market analyst"),
            "social": ("sentiment_report", "social media analyst"),
            "news": ("news_report", "news analyst"),
            "fundamentals": ("fundamentals_report", "fundamentals analyst"),
        }

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

        for analyst_type in analyst_nodes:
            report_key, label = analyst_report_keys[analyst_type]
            force_finalize_nodes[analyst_type] = create_force_finalize(
                self.quick_thinking_llm, report_key, label
            )

        # Create researcher and manager nodes
        bull_researcher_node = create_bull_researcher(
            self.quick_thinking_llm, self.bull_memory
        )
        bear_researcher_node = create_bear_researcher(
            self.quick_thinking_llm, self.bear_memory
        )
        research_manager_node = create_research_manager(
            self.deep_thinking_llm, self.invest_judge_memory
        )
        trader_node = create_trader(self.quick_thinking_llm, self.trader_memory)

        # Create risk analysis nodes
        aggressive_analyst = create_aggressive_debator(self.quick_thinking_llm)
        neutral_analyst = create_neutral_debator(self.quick_thinking_llm)
        conservative_analyst = create_conservative_debator(self.quick_thinking_llm)
        if self.trading_mode == "backtest":
            portfolio_manager_node = create_market_aware_portfolio_state_manager(
                self.deep_thinking_llm,
                self.portfolio_manager_memory,
                policy_config=self.portfolio_state_policy_config,
            )
        else:
            portfolio_manager_node = create_portfolio_manager(
                self.deep_thinking_llm, self.portfolio_manager_memory
            )

        # Cross-factor conflict detector (P0.1) runs after analysts, before the
        # debate. Live-only: backtest already captures contradictions inside the
        # MarketState classifier, and we avoid adding an LLM call per backtest day.
        conflict_enabled = self.trading_mode != "backtest"
        conflict_detector_node = (
            create_conflict_detector(self.quick_thinking_llm) if conflict_enabled else None
        )

        # Create workflow
        workflow = StateGraph(AgentState)

        # Add analyst nodes to the graph
        for analyst_type, node in analyst_nodes.items():
            node_name = f"{analyst_type.capitalize()} Analyst"
            force_name = f"Force Finalize {analyst_type.capitalize()}"
            workflow.add_node(node_name, self._timed_agent_node(node_name, node))
            workflow.add_node(
                f"Msg Clear {analyst_type.capitalize()}", delete_nodes[analyst_type]
            )
            workflow.add_node(f"tools_{analyst_type}", tool_nodes[analyst_type])
            workflow.add_node(
                force_name,
                self._timed_agent_node(force_name, force_finalize_nodes[analyst_type]),
            )

        # Add other nodes
        workflow.add_node(
            "Bull Researcher",
            self._timed_agent_node("Bull Researcher", bull_researcher_node),
        )
        workflow.add_node(
            "Bear Researcher",
            self._timed_agent_node("Bear Researcher", bear_researcher_node),
        )
        workflow.add_node(
            "Research Manager",
            self._timed_agent_node("Research Manager", research_manager_node),
        )
        workflow.add_node("Trader", self._timed_agent_node("Trader", trader_node))
        workflow.add_node(
            "Aggressive Analyst",
            self._timed_agent_node("Aggressive Analyst", aggressive_analyst),
        )
        workflow.add_node(
            "Neutral Analyst",
            self._timed_agent_node("Neutral Analyst", neutral_analyst),
        )
        workflow.add_node(
            "Conservative Analyst",
            self._timed_agent_node("Conservative Analyst", conservative_analyst),
        )
        workflow.add_node(
            "Portfolio Manager",
            self._timed_agent_node("Portfolio Manager", portfolio_manager_node),
        )
        if conflict_enabled:
            workflow.add_node(
                "Conflict Detector",
                self._timed_agent_node("Conflict Detector", conflict_detector_node),
            )

        # Define edges
        # Start with the first analyst
        first_analyst = selected_analysts[0]
        workflow.add_edge(START, f"{first_analyst.capitalize()} Analyst")

        # Connect analysts in sequence
        for i, analyst_type in enumerate(selected_analysts):
            current_analyst = f"{analyst_type.capitalize()} Analyst"
            current_tools = f"tools_{analyst_type}"
            current_clear = f"Msg Clear {analyst_type.capitalize()}"
            current_force = f"Force Finalize {analyst_type.capitalize()}"

            # Add conditional edges for current analyst
            workflow.add_conditional_edges(
                current_analyst,
                getattr(self.conditional_logic, f"should_continue_{analyst_type}"),
                [current_tools, current_force, current_clear],
            )
            workflow.add_edge(current_tools, current_analyst)
            workflow.add_edge(current_force, current_clear)

            # Connect to next analyst, or to the Conflict Detector / Bull Researcher
            # if this is the last analyst.
            if i < len(selected_analysts) - 1:
                next_analyst = f"{selected_analysts[i+1].capitalize()} Analyst"
                workflow.add_edge(current_clear, next_analyst)
            elif conflict_enabled:
                workflow.add_edge(current_clear, "Conflict Detector")
                workflow.add_edge("Conflict Detector", "Bull Researcher")
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

        return workflow
