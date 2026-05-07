# TradingAgents/graph/setup.py

from collections.abc import Callable
from typing import Any

from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from tradingagents.agents import (
    create_aggressive_debator,
    create_bear_researcher,
    create_bull_researcher,
    create_conservative_debator,
    create_critical_abort_terminal,
    create_fundamentals_analyst,
    create_market_analyst,
    create_msg_delete,
    create_neutral_debator,
    create_news_analyst,
    create_news_fact_checker,
    create_portfolio_manager,
    create_research_manager,
    create_risk_round_barrier,
    create_risk_synthesis,
    create_social_media_analyst,
    create_trader,
)
from tradingagents.agents.utils.agent_states import AgentState
from tradingagents.agents.utils.critical_abort import has_abort, raise_abort
from tradingagents.instruments import is_equity_pipeline_supported, resolve_instrument
from tradingagents.memory.news_evidence import NewsEvidenceStore

from ._consistency_guard import (
    check_claims_via_llm,
    extract_rm_claims,
    generate_research_packet_summary,
)
from ._graph_utils import assert_regime_consistent
from .conditional_logic import CRITICAL_ABORT_NODE, ConditionalLogic


class GraphSetup:
    """Handles the setup and configuration of the agent graph."""

    _REPORT_FIELD_BY_ANALYST = {
        "market": "market_report",
        "social": "sentiment_report",
        "news": "news_report",
        "fundamentals": "fundamentals_report",
    }

    def _should_short_circuit_to_critical_abort_terminal(self, state: AgentState) -> bool:
        return has_abort(state)

    @staticmethod
    def _route_after_preflight(state: AgentState, next_node: str) -> str:
        if has_abort(state):
            return CRITICAL_ABORT_NODE
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
    def _make_instrument_preflight_node() -> Callable[[AgentState], dict[str, Any]]:
        def instrument_preflight_node(state: AgentState) -> dict[str, Any]:
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

            detail = (
                "Unsupported instrument type for stock deep-dive: "
                f"{instrument.canonical_symbol} classified as "
                f"{instrument.instrument_type} ({instrument.asset_class})."
            )
            return {
                "instrument_key": instrument.instrument_key,
                "asset_class": instrument.asset_class,
                "instrument_type": instrument.instrument_type,
                "is_etf": instrument.is_etf,
                "is_inverse": instrument.is_inverse,
                "is_leveraged": instrument.is_leveraged,
                "analysis_status": "aborted",
                "terminal_action": "UNSUPPORTED_INSTRUMENT_TYPE",
                **raise_abort(
                    source="instrument_preflight",
                    reason="instrument_key_invalid",
                    detail=detail,
                    recoverable=False,
                ),
                "sender": "instrument_preflight",
            }

        return instrument_preflight_node

    @staticmethod
    def _make_market_regime_check_node() -> Callable[[AgentState], dict[str, Any]]:
        def market_regime_check_node(state: AgentState) -> dict[str, Any]:
            if "canonical_regime" not in state:
                return {"sender": "market_regime_check"}
            canonical = state["canonical_regime"]
            assert_regime_consistent(state.get("market_report") or "", canonical)
            return {"sender": "market_regime_check"}

        return market_regime_check_node

    def _make_rm_consistency_guard_node(self, llm: Any) -> Callable[[AgentState], dict[str, Any]]:
        def rm_consistency_guard_node(state: AgentState) -> dict[str, Any]:
            rm_text = state.get("investment_plan") or ""
            fundamentals = state.get("fundamentals_report") or ""
            if not fundamentals.strip():
                raise ValueError(
                    "rm_consistency_guard: fundamentals_report is missing — cannot verify RM claims"
                )
            claims = extract_rm_claims(rm_text)
            results = check_claims_via_llm(claims, fundamentals, llm)
            violations = []
            for r in results:
                if not r.get("ok"):
                    idx = r.get("index")
                    claim_text = (
                        claims[idx] if isinstance(idx, int) and 0 <= idx < len(claims) else ""
                    )
                    violations.append({"claim": claim_text, "reason": r.get("reason", "")})
            attempt = int(state.get("_rm_consistency_attempt") or 0)
            if not violations:
                summary = generate_research_packet_summary(
                    ticker=state.get("company_of_interest") or "",
                    trade_date=state.get("trade_date") or "",
                    investment_plan=rm_text,
                    fundamentals_report=fundamentals,
                )
                return {
                    "rm_consistency_status": "ok",
                    "consistency_violations": [],
                    "research_packet_summary": summary,
                    "sender": "rm_consistency_guard",
                }
            if attempt >= 1:
                details = "; ".join(v.get("reason", "") for v in violations)
                raise ValueError(
                    f"rm_consistency_guard: unresolved violations after corrective re-prompt — {details}"
                )
            return {
                "rm_consistency_status": "reprompt",
                "consistency_violations": violations,
                "research_packet_summary": "",
                "_rm_consistency_attempt": attempt + 1,
                "sender": "rm_consistency_guard",
            }

        return rm_consistency_guard_node

    def __init__(
        self,
        quick_thinking_llm: ChatOpenAI,
        mid_thinking_llm: ChatOpenAI,
        deep_thinking_llm: ChatOpenAI,
        bull_memory: Any,
        bear_memory: Any,
        trader_memory: Any,
        invest_judge_memory: Any,
        portfolio_manager_memory: Any,
        conditional_logic: ConditionalLogic,
        news_evidence_store: NewsEvidenceStore | None = None,
    ):
        """Initialize with required components."""
        self.quick_thinking_llm = quick_thinking_llm
        self.mid_thinking_llm = mid_thinking_llm
        self.deep_thinking_llm = deep_thinking_llm
        self.bull_memory = bull_memory
        self.bear_memory = bear_memory
        self.trader_memory = trader_memory
        self.invest_judge_memory = invest_judge_memory
        self.portfolio_manager_memory = portfolio_manager_memory
        self.conditional_logic = conditional_logic
        self.news_evidence_store = news_evidence_store or NewsEvidenceStore()

    def _create_risk_nodes(self) -> dict:
        """Create and return all 10 risk debate nodes."""
        return {
            "aggressive_r1": create_aggressive_debator(self.quick_thinking_llm, round_num=1),
            "conservative_r1": create_conservative_debator(self.quick_thinking_llm, round_num=1),
            "neutral_r1": create_neutral_debator(self.quick_thinking_llm, round_num=1),
            "risk_round_barrier": create_risk_round_barrier(),
            "aggressive_r2": create_aggressive_debator(self.quick_thinking_llm, round_num=2),
            "conservative_r2": create_conservative_debator(self.quick_thinking_llm, round_num=2),
            "neutral_r2": create_neutral_debator(self.quick_thinking_llm, round_num=2),
            "risk_synthesis": create_risk_synthesis(self.mid_thinking_llm),
            "critical_abort_terminal_node": create_critical_abort_terminal(),
            "portfolio_manager_node": create_portfolio_manager(
                self.deep_thinking_llm, self.portfolio_manager_memory
            ),
        }

    def _wire_risk_debate(
        self, workflow: StateGraph, nodes: dict, entry_node: Any = "Trader"
    ) -> None:
        """Add all 10 risk nodes to workflow and wire all edges."""
        workflow.add_node("Aggressive R1", nodes["aggressive_r1"])
        workflow.add_node("Conservative R1", nodes["conservative_r1"])
        workflow.add_node("Neutral R1", nodes["neutral_r1"])
        workflow.add_node("Risk Round Barrier", nodes["risk_round_barrier"])
        workflow.add_node("Aggressive R2", nodes["aggressive_r2"])
        workflow.add_node("Conservative R2", nodes["conservative_r2"])
        workflow.add_node("Neutral R2", nodes["neutral_r2"])
        workflow.add_node("Risk Synthesis", nodes["risk_synthesis"])
        workflow.add_node(CRITICAL_ABORT_NODE, nodes["critical_abort_terminal_node"])
        workflow.add_node("Portfolio Manager", nodes["portfolio_manager_node"])

        # Fan-out from entry → Round 1
        workflow.add_edge(entry_node, "Aggressive R1")
        workflow.add_edge(entry_node, "Conservative R1")
        workflow.add_edge(entry_node, "Neutral R1")
        # Round 1 → barrier
        workflow.add_edge("Aggressive R1", "Risk Round Barrier")
        workflow.add_edge("Conservative R1", "Risk Round Barrier")
        workflow.add_edge("Neutral R1", "Risk Round Barrier")
        # Barrier → Round 2
        workflow.add_edge("Risk Round Barrier", "Aggressive R2")
        workflow.add_edge("Risk Round Barrier", "Conservative R2")
        workflow.add_edge("Risk Round Barrier", "Neutral R2")
        # Round 2 → synthesis
        workflow.add_edge("Aggressive R2", "Risk Synthesis")
        workflow.add_edge("Conservative R2", "Risk Synthesis")
        workflow.add_edge("Neutral R2", "Risk Synthesis")
        # Synthesis → PM → END
        workflow.add_edge("Risk Synthesis", "Portfolio Manager")
        workflow.add_edge(CRITICAL_ABORT_NODE, END)
        workflow.add_edge("Portfolio Manager", END)

    def setup_graph(self, selected_analysts=None):
        """Set up and compile the agent workflow graph.

        Args:
            selected_analysts (list): List of analyst types to include. Options are:
                - "market": Market analyst
                - "news": News analyst
                - "fundamentals": Fundamentals analyst
                - "social": Social media analyst (disabled — scraper not yet implemented)
        """
        if selected_analysts is None:
            selected_analysts = ["market", "news", "fundamentals"]
        if len(selected_analysts) == 0:
            raise ValueError("Trading Agents Graph Setup Error: no analysts selected!")
        has_fundamentals = "fundamentals" in selected_analysts

        # Create analyst nodes
        analyst_nodes = {}
        delete_nodes = {}

        if "market" in selected_analysts:
            analyst_nodes["market"] = create_market_analyst(self.quick_thinking_llm)
            delete_nodes["market"] = create_msg_delete()

        if "social" in selected_analysts:
            analyst_nodes["social"] = create_social_media_analyst(self.quick_thinking_llm)
            delete_nodes["social"] = create_msg_delete()

        if "news" in selected_analysts:
            analyst_nodes["news"] = create_news_analyst(
                self.quick_thinking_llm,
                self.news_evidence_store,
            )
            delete_nodes["news"] = create_msg_delete()

        if "fundamentals" in selected_analysts:
            analyst_nodes["fundamentals"] = create_fundamentals_analyst(self.quick_thinking_llm)
            delete_nodes["fundamentals"] = create_msg_delete()

        # Create researcher and manager nodes
        bull_researcher_node = create_bull_researcher(self.mid_thinking_llm, self.bull_memory)
        bear_researcher_node = create_bear_researcher(self.mid_thinking_llm, self.bear_memory)
        research_manager_node = create_research_manager(
            self.deep_thinking_llm, self.invest_judge_memory
        )
        trader_node = create_trader(self.mid_thinking_llm, self.trader_memory)

        risk_nodes = self._create_risk_nodes()
        news_fact_checker_node = create_news_fact_checker(self.news_evidence_store)

        # Create workflow
        workflow = StateGraph(AgentState)

        # Add analyst nodes to the graph
        for analyst_type, node in analyst_nodes.items():
            workflow.add_node(f"{analyst_type.capitalize()} Analyst", node)
            workflow.add_node(f"Msg Clear {analyst_type.capitalize()}", delete_nodes[analyst_type])

        # Add other nodes
        workflow.add_node("Instrument Preflight", self._make_instrument_preflight_node())
        workflow.add_node("Bull Researcher", bull_researcher_node)
        workflow.add_node("Bear Researcher", bear_researcher_node)
        workflow.add_node("Research Manager", research_manager_node)
        if has_fundamentals:
            workflow.add_node(
                "RM Consistency Guard",
                self._make_rm_consistency_guard_node(self.quick_thinking_llm),
            )
        workflow.add_node("Trader", trader_node)
        workflow.add_node("News Fact Checker", news_fact_checker_node)
        if "market" in selected_analysts:
            workflow.add_node("Market Regime Check", self._make_market_regime_check_node())

        # Define edges
        # Start with deterministic instrument preflight
        workflow.add_edge(START, "Instrument Preflight")
        preflight_targets = {
            **{
                f"{analyst_type.capitalize()} Analyst": f"{analyst_type.capitalize()} Analyst"
                for analyst_type in selected_analysts
            },
            "Bull Researcher": "Bull Researcher",
            CRITICAL_ABORT_NODE: CRITICAL_ABORT_NODE,
        }
        workflow.add_conditional_edges(
            "Instrument Preflight",
            # Bind a copy at definition time so later selected_analysts changes
            # cannot affect this compiled graph's routing closure.
            lambda state, analysts=list(selected_analysts): self._route_after_preflight(
                state, self._resolve_next_analyst_node(state, analysts, 0)
            ),
            preflight_targets,
        )

        # Connect analysts in sequence
        for i, analyst_type in enumerate(selected_analysts):
            current_analyst = f"{analyst_type.capitalize()} Analyst"
            current_clear = f"Msg Clear {analyst_type.capitalize()}"

            # Analysts now go directly to their message clear node
            workflow.add_edge(current_analyst, current_clear)

            route_origin = current_clear
            if analyst_type == "news":
                workflow.add_edge(current_clear, "News Fact Checker")
                route_origin = "News Fact Checker"
            elif analyst_type == "market":
                workflow.add_edge(current_clear, "Market Regime Check")
                route_origin = "Market Regime Check"

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
                analysts: list[str] = None,
                start_index: int = i + 1,
            ) -> str:
                if analysts is None:
                    analysts = list(selected_analysts)
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
        if has_fundamentals:
            workflow.add_edge("Research Manager", "RM Consistency Guard")
            workflow.add_conditional_edges(
                "RM Consistency Guard",
                lambda s: (
                    "Research Manager" if s.get("rm_consistency_status") == "reprompt" else "Trader"
                ),
                {"Research Manager": "Research Manager", "Trader": "Trader"},
            )
        else:
            workflow.add_edge("Research Manager", "Trader")

        self._wire_risk_debate(workflow, risk_nodes)

        # Compile and return
        return workflow.compile()

    def build_debate_subgraph(self) -> Any:
        """Build a subgraph that starts from Bull Researcher (skips analysts).

        Use this to re-run the debate + trader + risk phases when analysts
        checkpoints are available. Reruns already carry analyst reports in state,
        so the LLM research-packet summary node is intentionally skipped here.
        """
        # Create researcher and manager nodes
        bull_researcher_node = create_bull_researcher(self.mid_thinking_llm, self.bull_memory)
        bear_researcher_node = create_bear_researcher(self.mid_thinking_llm, self.bear_memory)
        research_manager_node = create_research_manager(
            self.deep_thinking_llm, self.invest_judge_memory
        )
        trader_node = create_trader(self.mid_thinking_llm, self.trader_memory)

        risk_nodes = self._create_risk_nodes()

        workflow = StateGraph(AgentState)

        workflow.add_node("Bull Researcher", bull_researcher_node)
        workflow.add_node("Bear Researcher", bear_researcher_node)
        workflow.add_node("Research Manager", research_manager_node)
        workflow.add_node(
            "RM Consistency Guard", self._make_rm_consistency_guard_node(self.quick_thinking_llm)
        )
        workflow.add_node("Trader", trader_node)

        workflow.add_edge(START, "Bull Researcher")
        # Note: The debate subgraph intentionally omits "Portfolio Manager"
        # from routing targets. should_continue_debate() never returns it,
        # and the subgraph's terminal edge goes directly from PM to END.
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
        workflow.add_edge("Research Manager", "RM Consistency Guard")
        workflow.add_conditional_edges(
            "RM Consistency Guard",
            lambda s: (
                "Research Manager" if s.get("rm_consistency_status") == "reprompt" else "Trader"
            ),
            {"Research Manager": "Research Manager", "Trader": "Trader"},
        )

        self._wire_risk_debate(workflow, risk_nodes)

        return workflow.compile()

    def build_risk_subgraph(self) -> Any:
        """Build a subgraph that starts from the risk debate (skips analysts + debate + trader).

        Use this to re-run only the risk debate + PM phases when trader
        checkpoints are available. Reruns already carry trader and analyst
        context in state, so the LLM research-packet summary node is skipped.
        """

        risk_nodes = self._create_risk_nodes()

        workflow = StateGraph(AgentState)

        self._wire_risk_debate(workflow, risk_nodes, entry_node=START)

        return workflow.compile()
