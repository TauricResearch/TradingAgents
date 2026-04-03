# TradingAgents/graph/setup.py

from typing import Dict
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph, START
from langgraph.prebuilt import ToolNode

from tradingagents.agents import *
from tradingagents.agents.utils.agent_states import AgentState
from tradingagents.agents.utils.critical_abort import state_has_critical_abort
from tradingagents.instruments import is_equity_pipeline_supported, resolve_instrument
from tradingagents.memory.news_evidence import NewsEvidenceStore

from .conditional_logic import ConditionalLogic, CRITICAL_ABORT_NODE


class GraphSetup:
    """Handles the setup and configuration of the agent graph."""

    _REPORT_FIELD_BY_ANALYST = {
        "market": "market_report",
        "social": "sentiment_report",
        "news": "news_report",
        "fundamentals": "fundamentals_report",
    }

    def _should_short_circuit_to_critical_abort_terminal(self, state: AgentState) -> bool:
        return state_has_critical_abort(
            state, "market_report", "news_report", "fundamentals_report"
        )

    @staticmethod
    def _route_after_preflight(state: AgentState, next_node: str) -> str:
        if str(state.get("analysis_status") or "").strip().lower() == "aborted":
            return "END"
        return next_node

    @classmethod
    def _should_skip_analyst(cls, state: AgentState, analyst_type: str) -> bool:
        field_name = cls._REPORT_FIELD_BY_ANALYST.get(analyst_type)
        if not field_name:
            return False
        return bool(str(state.get(field_name) or "").strip())

    @classmethod
    def _resolve_next_analyst_node(
        cls, state: AgentState, selected_analysts: list[str], start_index: int = 0
    ) -> str:
        for analyst_type in selected_analysts[start_index:]:
            if cls._should_skip_analyst(state, analyst_type):
                continue
            return f"{analyst_type.capitalize()} Analyst"
        return "Bull Researcher"

    @staticmethod
    def _make_instrument_preflight_node():
        def instrument_preflight_node(state: AgentState) -> dict:
            instrument = resolve_instrument(
                state["company_of_interest"], source_context="trading_graph"
            )
            if is_equity_pipeline_supported(instrument):
                return {
                    "instrument_key": instrument.instrument_key,
                    "asset_class": instrument.asset_class,
                    "instrument_type": instrument.instrument_type,
                    "is_etf": instrument.is_etf,
                    "is_inverse": instrument.is_inverse,
                    "is_leveraged": instrument.is_leveraged,
                    "sender": "instrument_preflight",
                }

            return {
                "instrument_key": instrument.instrument_key,
                "asset_class": instrument.asset_class,
                "instrument_type": instrument.instrument_type,
                "is_etf": instrument.is_etf,
                "is_inverse": instrument.is_inverse,
                "is_leveraged": instrument.is_leveraged,
                "analysis_status": "aborted",
                "terminal_action": "UNSUPPORTED_INSTRUMENT_TYPE",
                "market_report": (
                    "[CRITICAL ABORT] Unsupported instrument type for stock deep-dive: "
                    f"{instrument.canonical_symbol} classified as "
                    f"{instrument.instrument_type} ({instrument.asset_class})."
                ),
                "sender": "instrument_preflight",
            }

        return instrument_preflight_node

    def __init__(
        self,
        quick_thinking_llm: ChatOpenAI,
        mid_thinking_llm: ChatOpenAI,
        deep_thinking_llm: ChatOpenAI,
        tool_nodes: Dict[str, ToolNode],
        bull_memory,
        bear_memory,
        trader_memory,
        invest_judge_memory,
        portfolio_manager_memory,
        conditional_logic: ConditionalLogic,
        news_evidence_store: NewsEvidenceStore | None = None,
    ):
        """Initialize with required components."""
        self.quick_thinking_llm = quick_thinking_llm
        self.mid_thinking_llm = mid_thinking_llm
        self.deep_thinking_llm = deep_thinking_llm
        self.tool_nodes = tool_nodes
        self.bull_memory = bull_memory
        self.bear_memory = bear_memory
        self.trader_memory = trader_memory
        self.invest_judge_memory = invest_judge_memory
        self.portfolio_manager_memory = portfolio_manager_memory
        self.conditional_logic = conditional_logic
        self.news_evidence_store = news_evidence_store or NewsEvidenceStore()

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
                self.mid_thinking_llm
            )
            delete_nodes["market"] = create_msg_delete()
            tool_nodes["market"] = self.tool_nodes["market"]

        if "social" in selected_analysts:
            analyst_nodes["social"] = create_social_media_analyst(
                self.mid_thinking_llm
            )
            delete_nodes["social"] = create_msg_delete()
            tool_nodes["social"] = self.tool_nodes["social"]

        if "news" in selected_analysts:
            analyst_nodes["news"] = create_news_analyst(
                self.mid_thinking_llm,
                self.news_evidence_store,
            )
            delete_nodes["news"] = create_msg_delete()
            tool_nodes["news"] = self.tool_nodes["news"]

        if "fundamentals" in selected_analysts:
            analyst_nodes["fundamentals"] = create_fundamentals_analyst(
                self.mid_thinking_llm
            )
            delete_nodes["fundamentals"] = create_msg_delete()
            tool_nodes["fundamentals"] = self.tool_nodes["fundamentals"]

        # Create researcher and manager nodes
        bull_researcher_node = create_bull_researcher(
            self.mid_thinking_llm, self.bull_memory
        )
        bear_researcher_node = create_bear_researcher(
            self.mid_thinking_llm, self.bear_memory
        )
        research_manager_node = create_research_manager(
            self.deep_thinking_llm, self.invest_judge_memory
        )
        trader_node = create_trader(self.mid_thinking_llm, self.trader_memory)

        # Create risk analysis nodes — 2 parallel rounds + synthesis
        aggressive_r1 = create_aggressive_debator(self.quick_thinking_llm, round_num=1)
        conservative_r1 = create_conservative_debator(self.quick_thinking_llm, round_num=1)
        neutral_r1 = create_neutral_debator(self.quick_thinking_llm, round_num=1)
        risk_round_barrier = create_risk_round_barrier()
        aggressive_r2 = create_aggressive_debator(self.quick_thinking_llm, round_num=2)
        conservative_r2 = create_conservative_debator(self.quick_thinking_llm, round_num=2)
        neutral_r2 = create_neutral_debator(self.quick_thinking_llm, round_num=2)
        risk_synthesis = create_risk_synthesis(self.mid_thinking_llm)
        critical_abort_terminal_node = create_critical_abort_terminal()
        news_fact_checker_node = create_news_fact_checker(self.news_evidence_store)
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
        workflow.add_node("Instrument Preflight", self._make_instrument_preflight_node())
        workflow.add_node("Bull Researcher", bull_researcher_node)
        workflow.add_node("Bear Researcher", bear_researcher_node)
        workflow.add_node("Research Manager", research_manager_node)
        workflow.add_node("Trader", trader_node)
        workflow.add_node("Aggressive R1", aggressive_r1)
        workflow.add_node("Conservative R1", conservative_r1)
        workflow.add_node("Neutral R1", neutral_r1)
        workflow.add_node("Risk Round Barrier", risk_round_barrier)
        workflow.add_node("Aggressive R2", aggressive_r2)
        workflow.add_node("Conservative R2", conservative_r2)
        workflow.add_node("Neutral R2", neutral_r2)
        workflow.add_node("Risk Synthesis", risk_synthesis)
        workflow.add_node(CRITICAL_ABORT_NODE, critical_abort_terminal_node)
        workflow.add_node("News Fact Checker", news_fact_checker_node)
        workflow.add_node("Portfolio Manager", portfolio_manager_node)

        # Define edges
        # Start with deterministic instrument preflight
        workflow.add_edge(START, "Instrument Preflight")
        preflight_targets = {
            **{
                f"{analyst_type.capitalize()} Analyst": f"{analyst_type.capitalize()} Analyst"
                for analyst_type in selected_analysts
            },
            "Bull Researcher": "Bull Researcher",
            "END": END,
        }
        workflow.add_conditional_edges(
            "Instrument Preflight",
            lambda state, analysts=list(selected_analysts): self._route_after_preflight(
                state, self._resolve_next_analyst_node(state, analysts, 0)
            ),
            preflight_targets,
        )

        # Connect analysts in sequence
        for i, analyst_type in enumerate(selected_analysts):
            current_analyst = f"{analyst_type.capitalize()} Analyst"
            current_tools = f"tools_{analyst_type}"
            current_clear = f"Msg Clear {analyst_type.capitalize()}"

            # Add conditional edges for current analyst
            workflow.add_conditional_edges(
                current_analyst,
                ConditionalLogic.make_should_continue(current_tools, current_clear),
                [current_tools, current_clear],
            )
            workflow.add_edge(current_tools, current_analyst)

            route_origin = current_clear
            if analyst_type == "news":
                workflow.add_edge(current_clear, "News Fact Checker")
                route_origin = "News Fact Checker"

            next_targets = {
                CRITICAL_ABORT_NODE: CRITICAL_ABORT_NODE,
                **{
                    f"{remaining.capitalize()} Analyst": f"{remaining.capitalize()} Analyst"
                    for remaining in selected_analysts[i + 1 :]
                },
                "Bull Researcher": "Bull Researcher",
            }

            def _route_after_clear(
                state: AgentState,
                analysts: list[str] = list(selected_analysts),
                start_index: int = i + 1,
            ) -> str:
                if self._should_short_circuit_to_critical_abort_terminal(state):
                    return CRITICAL_ABORT_NODE
                return self._resolve_next_analyst_node(state, analysts, start_index)

            workflow.add_conditional_edges(
                route_origin,
                _route_after_clear,
                next_targets,
            )

        # Add remaining edges
        workflow.add_conditional_edges(
            "Bull Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Bull Researcher": "Bull Researcher",
                "Bear Researcher": "Bear Researcher",
                "Research Manager": "Research Manager",
                CRITICAL_ABORT_NODE: CRITICAL_ABORT_NODE,
                "Portfolio Manager": "Portfolio Manager",
            },
        )
        workflow.add_conditional_edges(
            "Bear Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Bull Researcher": "Bull Researcher",
                "Bear Researcher": "Bear Researcher",
                "Research Manager": "Research Manager",
                CRITICAL_ABORT_NODE: CRITICAL_ABORT_NODE,
                "Portfolio Manager": "Portfolio Manager",
            },
        )
        workflow.add_edge("Research Manager", "Trader")

        # Round 1 — parallel fan-out from Trader
        workflow.add_edge("Trader", "Aggressive R1")
        workflow.add_edge("Trader", "Conservative R1")
        workflow.add_edge("Trader", "Neutral R1")
        # Round 1 — fan-in to barrier
        workflow.add_edge("Aggressive R1", "Risk Round Barrier")
        workflow.add_edge("Conservative R1", "Risk Round Barrier")
        workflow.add_edge("Neutral R1", "Risk Round Barrier")
        # Round 2 — parallel fan-out from barrier
        workflow.add_edge("Risk Round Barrier", "Aggressive R2")
        workflow.add_edge("Risk Round Barrier", "Conservative R2")
        workflow.add_edge("Risk Round Barrier", "Neutral R2")
        # Round 2 — fan-in to synthesis
        workflow.add_edge("Aggressive R2", "Risk Synthesis")
        workflow.add_edge("Conservative R2", "Risk Synthesis")
        workflow.add_edge("Neutral R2", "Risk Synthesis")
        # Synthesis → PM
        workflow.add_edge("Risk Synthesis", "Portfolio Manager")

        workflow.add_edge(CRITICAL_ABORT_NODE, END)
        workflow.add_edge("Portfolio Manager", END)

        # Compile and return
        return workflow.compile()

    def build_debate_subgraph(self):
        """Build a subgraph that starts from Bull Researcher (skips analysts).

        Use this to re-run the debate + trader + risk phases when analysts
        checkpoints are available. Reruns already carry analyst reports in state,
        so the LLM research-packet summary node is intentionally skipped here.
        """
        # Create researcher and manager nodes
        bull_researcher_node = create_bull_researcher(
            self.mid_thinking_llm, self.bull_memory
        )
        bear_researcher_node = create_bear_researcher(
            self.mid_thinking_llm, self.bear_memory
        )
        research_manager_node = create_research_manager(
            self.deep_thinking_llm, self.invest_judge_memory
        )
        trader_node = create_trader(self.mid_thinking_llm, self.trader_memory)

        # Risk debate — 2 parallel rounds + synthesis
        aggressive_r1 = create_aggressive_debator(self.quick_thinking_llm, round_num=1)
        conservative_r1 = create_conservative_debator(self.quick_thinking_llm, round_num=1)
        neutral_r1 = create_neutral_debator(self.quick_thinking_llm, round_num=1)
        risk_round_barrier = create_risk_round_barrier()
        aggressive_r2 = create_aggressive_debator(self.quick_thinking_llm, round_num=2)
        conservative_r2 = create_conservative_debator(self.quick_thinking_llm, round_num=2)
        neutral_r2 = create_neutral_debator(self.quick_thinking_llm, round_num=2)
        risk_synthesis = create_risk_synthesis(self.mid_thinking_llm)
        critical_abort_terminal_node = create_critical_abort_terminal()
        portfolio_manager_node = create_portfolio_manager(
            self.deep_thinking_llm, self.portfolio_manager_memory
        )

        workflow = StateGraph(AgentState)

        workflow.add_node("Bull Researcher", bull_researcher_node)
        workflow.add_node("Bear Researcher", bear_researcher_node)
        workflow.add_node("Research Manager", research_manager_node)
        workflow.add_node("Trader", trader_node)
        workflow.add_node("Aggressive R1", aggressive_r1)
        workflow.add_node("Conservative R1", conservative_r1)
        workflow.add_node("Neutral R1", neutral_r1)
        workflow.add_node("Risk Round Barrier", risk_round_barrier)
        workflow.add_node("Aggressive R2", aggressive_r2)
        workflow.add_node("Conservative R2", conservative_r2)
        workflow.add_node("Neutral R2", neutral_r2)
        workflow.add_node("Risk Synthesis", risk_synthesis)
        workflow.add_node(CRITICAL_ABORT_NODE, critical_abort_terminal_node)
        workflow.add_node("Portfolio Manager", portfolio_manager_node)

        workflow.add_edge(START, "Bull Researcher")
        workflow.add_conditional_edges(
            "Bull Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Bull Researcher": "Bull Researcher",
                "Bear Researcher": "Bear Researcher",
                "Research Manager": "Research Manager",
                CRITICAL_ABORT_NODE: CRITICAL_ABORT_NODE,
            },
        )
        workflow.add_conditional_edges(
            "Bear Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Bull Researcher": "Bull Researcher",
                "Bear Researcher": "Bear Researcher",
                "Research Manager": "Research Manager",
                CRITICAL_ABORT_NODE: CRITICAL_ABORT_NODE,
            },
        )
        workflow.add_edge("Research Manager", "Trader")

        # Round 1 — parallel fan-out from Trader
        workflow.add_edge("Trader", "Aggressive R1")
        workflow.add_edge("Trader", "Conservative R1")
        workflow.add_edge("Trader", "Neutral R1")
        # Round 1 — fan-in to barrier
        workflow.add_edge("Aggressive R1", "Risk Round Barrier")
        workflow.add_edge("Conservative R1", "Risk Round Barrier")
        workflow.add_edge("Neutral R1", "Risk Round Barrier")
        # Round 2 — parallel fan-out from barrier
        workflow.add_edge("Risk Round Barrier", "Aggressive R2")
        workflow.add_edge("Risk Round Barrier", "Conservative R2")
        workflow.add_edge("Risk Round Barrier", "Neutral R2")
        # Round 2 — fan-in to synthesis
        workflow.add_edge("Aggressive R2", "Risk Synthesis")
        workflow.add_edge("Conservative R2", "Risk Synthesis")
        workflow.add_edge("Neutral R2", "Risk Synthesis")
        # Synthesis → PM
        workflow.add_edge("Risk Synthesis", "Portfolio Manager")

        workflow.add_edge(CRITICAL_ABORT_NODE, END)
        workflow.add_edge("Portfolio Manager", END)

        return workflow.compile()

    def build_risk_subgraph(self):
        """Build a subgraph that starts from the risk debate (skips analysts + debate + trader).

        Use this to re-run only the risk debate + PM phases when trader
        checkpoints are available. Reruns already carry trader and analyst
        context in state, so the LLM research-packet summary node is skipped.
        """

        # Risk debate — 2 parallel rounds + synthesis
        aggressive_r1 = create_aggressive_debator(self.quick_thinking_llm, round_num=1)
        conservative_r1 = create_conservative_debator(self.quick_thinking_llm, round_num=1)
        neutral_r1 = create_neutral_debator(self.quick_thinking_llm, round_num=1)
        risk_round_barrier = create_risk_round_barrier()
        aggressive_r2 = create_aggressive_debator(self.quick_thinking_llm, round_num=2)
        conservative_r2 = create_conservative_debator(self.quick_thinking_llm, round_num=2)
        neutral_r2 = create_neutral_debator(self.quick_thinking_llm, round_num=2)
        risk_synthesis = create_risk_synthesis(self.mid_thinking_llm)
        critical_abort_terminal_node = create_critical_abort_terminal()
        portfolio_manager_node = create_portfolio_manager(
            self.deep_thinking_llm, self.portfolio_manager_memory
        )

        workflow = StateGraph(AgentState)

        workflow.add_node("Aggressive R1", aggressive_r1)
        workflow.add_node("Conservative R1", conservative_r1)
        workflow.add_node("Neutral R1", neutral_r1)
        workflow.add_node("Risk Round Barrier", risk_round_barrier)
        workflow.add_node("Aggressive R2", aggressive_r2)
        workflow.add_node("Conservative R2", conservative_r2)
        workflow.add_node("Neutral R2", neutral_r2)
        workflow.add_node("Risk Synthesis", risk_synthesis)
        workflow.add_node(CRITICAL_ABORT_NODE, critical_abort_terminal_node)
        workflow.add_node("Portfolio Manager", portfolio_manager_node)

        # Round 1 — parallel fan-out from preloaded rerun state
        workflow.add_edge(START, "Aggressive R1")
        workflow.add_edge(START, "Conservative R1")
        workflow.add_edge(START, "Neutral R1")
        # Round 1 — fan-in to barrier
        workflow.add_edge("Aggressive R1", "Risk Round Barrier")
        workflow.add_edge("Conservative R1", "Risk Round Barrier")
        workflow.add_edge("Neutral R1", "Risk Round Barrier")
        # Round 2 — parallel fan-out from barrier
        workflow.add_edge("Risk Round Barrier", "Aggressive R2")
        workflow.add_edge("Risk Round Barrier", "Conservative R2")
        workflow.add_edge("Risk Round Barrier", "Neutral R2")
        # Round 2 — fan-in to synthesis
        workflow.add_edge("Aggressive R2", "Risk Synthesis")
        workflow.add_edge("Conservative R2", "Risk Synthesis")
        workflow.add_edge("Neutral R2", "Risk Synthesis")
        # Synthesis → PM
        workflow.add_edge("Risk Synthesis", "Portfolio Manager")

        workflow.add_edge(CRITICAL_ABORT_NODE, END)
        workflow.add_edge("Portfolio Manager", END)

        return workflow.compile()
