"""Experimental graph builders for the agent-structure A/B experiment.

Each builder produces a ``StateGraph`` with the same input/output contract
as the baseline ``GraphSetup`` (reads ``company_of_interest`` / ``trade_date``,
writes ``final_trade_decision``) so the harness, memory log, and report
writers can consume any variation interchangeably.

Variations:

- ``baseline`` — delegates to the existing ``GraphSetup``.
- ``no_debate`` — single Critic replaces Bull/Bear; single Risk Reviewer
  replaces Aggressive/Conservative/Neutral.
- ``risk_officer`` — keeps Bull/Bear; replaces 3-way risk debate with a
  deterministic Risk Officer that can hard-veto via post-PM enforcement.
- ``quant_augmented`` — baseline pipeline plus a deterministic Quant
  Analyst node that injects technical signals into ``market_report``
  before the Bull/Bear stage.

The veto enforcer for ``risk_officer`` rewrites the PM's rendered
``final_trade_decision`` markdown when a hard veto is set, capping
``Buy`` / ``Overweight`` ratings at ``Hold``. ``Sell`` / ``Underweight``
are left alone — the floor is on caution, not on direction.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List

from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from tradingagents.agents import (
    create_bear_researcher,
    create_bull_researcher,
    create_fundamentals_analyst,
    create_market_analyst,
    create_msg_delete,
    create_news_analyst,
    create_portfolio_manager,
    create_research_manager,
    create_social_media_analyst,
    create_trader,
)
from tradingagents.agents.analysts.quant_analyst import create_quant_analyst
from tradingagents.agents.researchers.critic import create_critic
from tradingagents.agents.risk_mgmt.risk_officer import create_risk_officer
from tradingagents.agents.risk_mgmt.risk_reviewer import create_risk_reviewer
from tradingagents.agents.utils.agent_states import AgentState

from .conditional_logic import ConditionalLogic
from .setup import GraphSetup

VALID_VARIATIONS = ("baseline", "no_debate", "risk_officer", "quant_augmented")


def _add_analyst_chain(
    workflow: StateGraph,
    selected_analysts: Iterable[str],
    analyst_factories: Dict[str, Any],
    tool_nodes: Dict[str, ToolNode],
    quick_llm: Any,
    conditional_logic: ConditionalLogic,
    next_after_last: str,
) -> str:
    """Wire the analyst chain into ``workflow`` and return the entry-node name.

    Mirrors the baseline ``GraphSetup`` shape (analyst → tools loop, then
    Msg Clear, then next analyst), terminating at ``next_after_last``.
    """
    selected = list(selected_analysts)
    if not selected:
        raise ValueError("no analysts selected")

    for analyst_type in selected:
        node = analyst_factories[analyst_type](quick_llm)
        workflow.add_node(f"{analyst_type.capitalize()} Analyst", node)
        workflow.add_node(f"Msg Clear {analyst_type.capitalize()}", create_msg_delete())
        workflow.add_node(f"tools_{analyst_type}", tool_nodes[analyst_type])

    for i, analyst_type in enumerate(selected):
        current_analyst = f"{analyst_type.capitalize()} Analyst"
        current_tools = f"tools_{analyst_type}"
        current_clear = f"Msg Clear {analyst_type.capitalize()}"

        workflow.add_conditional_edges(
            current_analyst,
            getattr(conditional_logic, f"should_continue_{analyst_type}"),
            [current_tools, current_clear],
        )
        workflow.add_edge(current_tools, current_analyst)

        if i < len(selected) - 1:
            workflow.add_edge(current_clear, f"{selected[i + 1].capitalize()} Analyst")
        else:
            workflow.add_edge(current_clear, next_after_last)

    return f"{selected[0].capitalize()} Analyst"


_RATING_LINE_RE = re.compile(r"^(\*\*Rating\*\*:\s*)(Buy|Overweight|Hold|Underweight|Sell)\s*$", re.MULTILINE)


def _enforce_veto_on_decision(decision_md: str, veto_reason: str) -> str:
    """Cap a Buy/Overweight rating at Hold when a veto is set; leave Sell/Underweight."""
    if not veto_reason:
        return decision_md

    def _cap(match: re.Match) -> str:
        rating = match.group(2)
        if rating in ("Buy", "Overweight"):
            return f"{match.group(1)}Hold"
        return match.group(0)

    rewritten = _RATING_LINE_RE.sub(_cap, decision_md, count=1)
    note = f"\n\n**Risk Officer Veto Applied**: {veto_reason} Rating capped at Hold."
    return rewritten + note


def _veto_enforcer_node(state) -> dict:
    veto = state.get("risk_officer_veto", "") or ""
    decision = state.get("final_trade_decision", "") or ""
    if not veto or not decision:
        return {}
    return {"final_trade_decision": _enforce_veto_on_decision(decision, veto)}


def _analyst_factories() -> Dict[str, Any]:
    return {
        "market": create_market_analyst,
        "social": create_social_media_analyst,
        "news": create_news_analyst,
        "fundamentals": create_fundamentals_analyst,
    }


def build_no_debate_graph(
    quick_llm: Any,
    deep_llm: Any,
    tool_nodes: Dict[str, ToolNode],
    conditional_logic: ConditionalLogic,
    selected_analysts: List[str],
) -> StateGraph:
    """Single Critic + single Risk Reviewer; everything else baseline."""
    workflow = StateGraph(AgentState)

    _add_analyst_chain(
        workflow,
        selected_analysts,
        _analyst_factories(),
        tool_nodes,
        quick_llm,
        conditional_logic,
        next_after_last="Critic",
    )

    workflow.add_node("Critic", create_critic(quick_llm))
    workflow.add_node("Research Manager", create_research_manager(deep_llm))
    workflow.add_node("Trader", create_trader(quick_llm))
    workflow.add_node("Risk Reviewer", create_risk_reviewer(quick_llm))
    workflow.add_node("Portfolio Manager", create_portfolio_manager(deep_llm))

    workflow.add_edge(START, f"{selected_analysts[0].capitalize()} Analyst")
    workflow.add_edge("Critic", "Research Manager")
    workflow.add_edge("Research Manager", "Trader")
    workflow.add_edge("Trader", "Risk Reviewer")
    workflow.add_edge("Risk Reviewer", "Portfolio Manager")
    workflow.add_edge("Portfolio Manager", END)

    return workflow


def build_risk_officer_graph(
    quick_llm: Any,
    deep_llm: Any,
    tool_nodes: Dict[str, ToolNode],
    conditional_logic: ConditionalLogic,
    selected_analysts: List[str],
) -> StateGraph:
    """Baseline analysts + Bull/Bear; replace 3-way risk with Risk Officer + veto enforcer."""
    workflow = StateGraph(AgentState)

    _add_analyst_chain(
        workflow,
        selected_analysts,
        _analyst_factories(),
        tool_nodes,
        quick_llm,
        conditional_logic,
        next_after_last="Bull Researcher",
    )

    workflow.add_node("Bull Researcher", create_bull_researcher(quick_llm))
    workflow.add_node("Bear Researcher", create_bear_researcher(quick_llm))
    workflow.add_node("Research Manager", create_research_manager(deep_llm))
    workflow.add_node("Trader", create_trader(quick_llm))
    workflow.add_node("Risk Officer", create_risk_officer(quick_llm))
    workflow.add_node("Portfolio Manager", create_portfolio_manager(deep_llm))
    workflow.add_node("Veto Enforcer", _veto_enforcer_node)

    workflow.add_edge(START, f"{selected_analysts[0].capitalize()} Analyst")
    workflow.add_conditional_edges(
        "Bull Researcher",
        conditional_logic.should_continue_debate,
        {"Bear Researcher": "Bear Researcher", "Research Manager": "Research Manager"},
    )
    workflow.add_conditional_edges(
        "Bear Researcher",
        conditional_logic.should_continue_debate,
        {"Bull Researcher": "Bull Researcher", "Research Manager": "Research Manager"},
    )
    workflow.add_edge("Research Manager", "Trader")
    workflow.add_edge("Trader", "Risk Officer")
    workflow.add_edge("Risk Officer", "Portfolio Manager")
    workflow.add_edge("Portfolio Manager", "Veto Enforcer")
    workflow.add_edge("Veto Enforcer", END)

    return workflow


def build_quant_augmented_graph(
    quick_llm: Any,
    deep_llm: Any,
    tool_nodes: Dict[str, ToolNode],
    conditional_logic: ConditionalLogic,
    selected_analysts: List[str],
) -> StateGraph:
    """Baseline + a Quant Analyst node that runs after the LLM analysts and
    appends deterministic technical signals into ``market_report`` before
    the Bull/Bear stage."""
    workflow = StateGraph(AgentState)

    _add_analyst_chain(
        workflow,
        selected_analysts,
        _analyst_factories(),
        tool_nodes,
        quick_llm,
        conditional_logic,
        next_after_last="Quant Analyst",
    )

    workflow.add_node("Quant Analyst", create_quant_analyst())
    workflow.add_node("Bull Researcher", create_bull_researcher(quick_llm))
    workflow.add_node("Bear Researcher", create_bear_researcher(quick_llm))
    workflow.add_node("Research Manager", create_research_manager(deep_llm))
    workflow.add_node("Trader", create_trader(quick_llm))
    # Reuse single Risk Reviewer here so the quant signal gets a clean,
    # short risk pass rather than three personalities.
    workflow.add_node("Risk Reviewer", create_risk_reviewer(quick_llm))
    workflow.add_node("Portfolio Manager", create_portfolio_manager(deep_llm))

    workflow.add_edge(START, f"{selected_analysts[0].capitalize()} Analyst")
    workflow.add_edge("Quant Analyst", "Bull Researcher")
    workflow.add_conditional_edges(
        "Bull Researcher",
        conditional_logic.should_continue_debate,
        {"Bear Researcher": "Bear Researcher", "Research Manager": "Research Manager"},
    )
    workflow.add_conditional_edges(
        "Bear Researcher",
        conditional_logic.should_continue_debate,
        {"Bull Researcher": "Bull Researcher", "Research Manager": "Research Manager"},
    )
    workflow.add_edge("Research Manager", "Trader")
    workflow.add_edge("Trader", "Risk Reviewer")
    workflow.add_edge("Risk Reviewer", "Portfolio Manager")
    workflow.add_edge("Portfolio Manager", END)

    return workflow


def build_variation_graph(
    variation: str,
    quick_llm: Any,
    deep_llm: Any,
    tool_nodes: Dict[str, ToolNode],
    conditional_logic: ConditionalLogic,
    selected_analysts: List[str],
) -> StateGraph:
    """Dispatch to the right graph builder. ``baseline`` uses ``GraphSetup``."""
    if variation == "baseline":
        return GraphSetup(quick_llm, deep_llm, tool_nodes, conditional_logic).setup_graph(selected_analysts)
    if variation == "no_debate":
        return build_no_debate_graph(quick_llm, deep_llm, tool_nodes, conditional_logic, selected_analysts)
    if variation == "risk_officer":
        return build_risk_officer_graph(quick_llm, deep_llm, tool_nodes, conditional_logic, selected_analysts)
    if variation == "quant_augmented":
        return build_quant_augmented_graph(quick_llm, deep_llm, tool_nodes, conditional_logic, selected_analysts)
    raise ValueError(f"Unknown variation '{variation}'. Valid: {VALID_VARIATIONS}")
