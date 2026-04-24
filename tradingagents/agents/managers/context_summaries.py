"""Summary nodes that compress analyst and debate context for downstream agents."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from tradingagents.agents.utils.agent_states import AgentState
from tradingagents.agents.utils.summary_context import (
    build_investment_debate_summary,
    build_research_packet,
    build_risk_debate_summary,
)


def _build_investment_debate_input(prior_summary: str, current_response: str) -> str:
    return f"""Previous summary:
{prior_summary or 'No prior summary.'}

Latest response:
{current_response}"""


def _build_risk_debate_input(prior_summary: str, latest_speaker: str, current_response: str) -> str:
    return f"""Previous summary:
{prior_summary or 'No prior summary.'}

Latest speaker:
{latest_speaker}

Latest response:
{current_response}"""


def create_research_packet_summary(llm: Any) -> Callable[[AgentState], dict[str, Any]]:
    # TODO(structured-contracts): remove after Phase 6 — this node is no longer
    # wired into any graph.  build_research_packet() is now called inline by
    # each consumer (bull_researcher, bear_researcher, research_manager, etc.).
    def research_packet_summary_node(state: AgentState) -> dict[str, Any]:
        if not any(
            (
                state.get("market_report"),
                state.get("market_report_structured"),
                state.get("sentiment_report"),
                state.get("news_report"),
                state.get("fundamentals_report"),
                state.get("macro_regime_report"),
                state.get("scanner_graph_context_text"),
            )
        ):
            return {
                "research_packet_summary": "",
                "sender": "research_packet_summary",
            }

        return {
            "research_packet_summary": build_research_packet(state),
            "sender": "research_packet_summary",
        }

    return research_packet_summary_node


def create_investment_debate_summary(llm: Any) -> Callable[[AgentState], dict[str, Any]]:
    # TODO(structured-contracts): remove after Phase 6 — this node is no longer
    # wired into any graph.  build_investment_debate_summary() is now called
    # inline by research_manager.
    def investment_debate_summary_node(state: AgentState) -> dict[str, Any]:

        debate_state = state["investment_debate_state"]
        summary = build_investment_debate_summary(debate_state) or "Investment debate in progress..."

        return {
            "investment_debate_state": {
                **debate_state,
                "summary": summary,
            },
            "sender": "investment_debate_summary",
        }

    return investment_debate_summary_node


def create_risk_debate_summary(llm: Any) -> Callable[[AgentState], dict[str, Any]]:
    def risk_debate_summary_node(state: AgentState) -> dict[str, Any]:
        debate_state = state["risk_debate_state"]
        summary = build_risk_debate_summary(debate_state) or "Risk debate in progress..."

        return {
            "risk_debate_state": {
                **debate_state,
                "summary": summary,
            },
            "sender": "risk_debate_summary",
        }

    return risk_debate_summary_node
