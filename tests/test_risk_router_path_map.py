"""Shared-router / path_map completeness (#1088).

Both `should_continue_risk_analysis` (three risk edges) and
`should_continue_debate` (two research-debate edges) are single routers whose
return set is larger than any one edge previously mapped. Each edge now shares a
complete path map (`RISK_ANALYSIS_PATH_MAP` / `DEBATE_PATH_MAP`), so a
fall-through return can never hit a missing entry -- which would crash LangGraph
mid-run on prompt/i18n/refactor drift in the speaker labels.
"""

from typing import TypedDict

import pytest
from langgraph.graph import END, START, StateGraph

from tradingagents.graph.conditional_logic import ConditionalLogic
from tradingagents.graph.setup import DEBATE_PATH_MAP, RISK_ANALYSIS_PATH_MAP


def _state(latest_speaker, count=0):
    return {"risk_debate_state": {"latest_speaker": latest_speaker, "count": count}}


def _debate_state(current_response="", count=0):
    return {"investment_debate_state": {"current_response": current_response, "count": count}}


@pytest.mark.unit
@pytest.mark.parametrize(
    "latest_speaker",
    [
        "Aggressive",
        "Aggressive Analyst",
        "Conservative",
        "Conservative Analyst",
        "Neutral",
        "Neutral Analyst",
        "",  # drift: empty label
        "Aggressive Risk Analyst",  # drift: node renamed
        "Agresivo",  # drift: i18n / translated label
    ],
)
def test_router_return_always_routable(latest_speaker):
    logic = ConditionalLogic(max_risk_discuss_rounds=1)
    target = logic.should_continue_risk_analysis(_state(latest_speaker))
    assert target in RISK_ANALYSIS_PATH_MAP


@pytest.mark.unit
def test_router_terminates_at_round_limit():
    logic = ConditionalLogic(max_risk_discuss_rounds=1)
    # count >= 3 * rounds routes to the Portfolio Manager (debate ends)
    assert logic.should_continue_risk_analysis(_state("Neutral", count=3)) == "Portfolio Manager"


@pytest.mark.unit
def test_path_map_covers_full_router_range():
    logic = ConditionalLogic(max_risk_discuss_rounds=1)
    returns = {
        logic.should_continue_risk_analysis(_state(s, c))
        for s in ("Aggressive", "Conservative", "Neutral", "drift")
        for c in (0, 99)
    }
    # Every value the router can emit is a key in the shared map...
    assert returns <= set(RISK_ANALYSIS_PATH_MAP)
    # ...and the terminal target is reachable.
    assert "Portfolio Manager" in returns


@pytest.mark.unit
@pytest.mark.parametrize(
    "current_response",
    [
        "Unlabelled opening case",
        "Bull Researcher: legacy labelled body",
        "Bear Researcher: legacy labelled body",
        "",  # empty model output
        "Optimista",  # i18n / translated prose
    ],
)
def test_debate_router_return_always_routable_without_speaker_labels(current_response):
    logic = ConditionalLogic(max_debate_rounds=1)
    target = logic.should_continue_debate(_debate_state(current_response))
    assert target in DEBATE_PATH_MAP


@pytest.mark.unit
@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (0, "Bull Researcher"),
        (1, "Bear Researcher"),
        (2, "Bull Researcher"),
        (3, "Bear Researcher"),
        (4, "Research Manager"),
    ],
)
def test_debate_router_alternates_by_completed_turn_count(count, expected):
    logic = ConditionalLogic(max_debate_rounds=2)

    assert (
        logic.should_continue_debate(
            _debate_state("prose deliberately has no structural speaker label", count)
        )
        == expected
    )


@pytest.mark.unit
def test_debate_router_reaches_manager_only_after_complete_round():
    logic = ConditionalLogic(max_debate_rounds=1)

    assert logic.should_continue_debate(_debate_state(count=1)) == "Bear Researcher"
    assert logic.should_continue_debate(_debate_state(count=2)) == "Research Manager"


@pytest.mark.unit
def test_debate_path_map_covers_full_router_range():
    logic = ConditionalLogic(max_debate_rounds=2)
    returns = {
        logic.should_continue_debate(_debate_state(s, c))
        for s in ("unlabelled prose", "legacy label", "drift")
        for c in range(5)
    }
    assert returns <= set(DEBATE_PATH_MAP)
    assert "Research Manager" in returns  # terminal reachable


class _DebateGraphState(TypedDict):
    investment_debate_state: dict
    visited: list[str]
    research_rating: str


@pytest.mark.unit
def test_langgraph_debate_path_executes_complete_two_round_sequence():
    logic = ConditionalLogic(max_debate_rounds=2)
    workflow = StateGraph(_DebateGraphState)

    def record_turn(role: str):
        def node(state):
            debate = state["investment_debate_state"]
            return {
                "investment_debate_state": {
                    **debate,
                    "current_response": f"{role} prose without a speaker label",
                    "count": debate["count"] + 1,
                },
                "visited": [*state["visited"], role],
            }

        return node

    def research_manager(state):
        return {
            "visited": [*state["visited"], "manager.research"],
            "research_rating": "Overweight",
        }

    workflow.add_node("Bull Researcher", record_turn("researcher.bull"))
    workflow.add_node("Bear Researcher", record_turn("researcher.bear"))
    workflow.add_node("Research Manager", research_manager)
    workflow.add_edge(START, "Bull Researcher")
    for node_name in ("Bull Researcher", "Bear Researcher"):
        workflow.add_conditional_edges(node_name, logic.should_continue_debate, DEBATE_PATH_MAP)
    workflow.add_edge("Research Manager", END)

    result = workflow.compile().invoke(
        {
            "investment_debate_state": {"current_response": "", "count": 0},
            "visited": [],
            "research_rating": "",
        }
    )

    assert result["visited"] == [
        "researcher.bull",
        "researcher.bear",
        "researcher.bull",
        "researcher.bear",
        "manager.research",
    ]
    assert result["investment_debate_state"]["count"] == 4
    assert result["research_rating"] == "Overweight"
