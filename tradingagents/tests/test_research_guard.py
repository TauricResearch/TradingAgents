import time

import tradingagents.graph.setup as graph_setup_module
from tradingagents.graph.setup import GraphSetup


def _setup() -> GraphSetup:
    return GraphSetup(
        quick_thinking_llm=None,
        deep_thinking_llm=None,
        tool_nodes={},
        bull_memory=None,
        bear_memory=None,
        trader_memory=None,
        invest_judge_memory=None,
        portfolio_manager_memory=None,
        conditional_logic=None,
        research_node_timeout_secs=0.01,
    )


def test_manager_guard_fallback_marks_degraded_synthesis():
    setup = _setup()
    state = {
        "investment_debate_state": {
            "history": "Bull Analyst: case",
            "bull_history": "Bull Analyst: case",
            "bear_history": "",
            "current_response": "Bull Analyst: case",
            "judge_decision": "",
            "count": 1,
            "research_status": "full",
            "research_mode": "debate",
            "timed_out_nodes": [],
            "degraded_reason": None,
            "covered_dimensions": ["bull"],
            "manager_confidence": None,
        }
    }

    result = setup._apply_research_fallback(
        state,
        node_name="Research Manager",
        dimension="manager",
        reason="research_manager_timeout",
        started_at=0.0,
    )

    debate = result["investment_debate_state"]
    assert debate["research_status"] == "degraded"
    assert debate["research_mode"] == "degraded_synthesis"
    assert debate["timed_out_nodes"] == ["Research Manager"]
    assert result["investment_plan"].startswith("Recommendation: HOLD")


def test_bull_guard_success_records_coverage():
    setup = _setup()
    state = {
        "investment_debate_state": {
            "history": "",
            "bull_history": "",
            "bear_history": "",
            "current_response": "",
            "judge_decision": "",
            "count": 0,
            "research_status": "full",
            "research_mode": "debate",
            "timed_out_nodes": [],
            "degraded_reason": None,
            "covered_dimensions": [],
            "manager_confidence": None,
        }
    }
    result = {
        "investment_debate_state": {
            "history": "Bull Analyst: ok",
            "bull_history": "Bull Analyst: ok",
            "bear_history": "",
            "current_response": "Bull Analyst: ok",
            "judge_decision": "",
            "count": 1,
        }
    }

    updated = setup._apply_research_success(state, result, dimension="bull")
    debate = updated["investment_debate_state"]
    assert debate["research_status"] == "full"
    assert debate["research_mode"] == "debate"
    assert debate["covered_dimensions"] == ["bull"]


def test_manager_success_sets_confidence_without_changing_shape():
    setup = _setup()
    state = {
        "investment_debate_state": {
            "history": "Bull Analyst: case\nBear Analyst: counter",
            "bull_history": "Bull Analyst: case",
            "bear_history": "Bear Analyst: counter",
            "current_response": "Bear Analyst: counter",
            "judge_decision": "",
            "count": 2,
            "research_status": "full",
            "research_mode": "debate",
            "timed_out_nodes": [],
            "degraded_reason": None,
            "covered_dimensions": ["bull", "bear"],
            "manager_confidence": None,
        }
    }
    result = {
        "investment_debate_state": {
            "history": "Bull Analyst: case\nBear Analyst: counter",
            "bull_history": "Bull Analyst: case",
            "bear_history": "Bear Analyst: counter",
            "current_response": "Recommendation: BUY",
            "judge_decision": "Recommendation: BUY",
            "count": 2,
        },
        "investment_plan": "Recommendation: BUY",
    }

    updated = setup._apply_research_success(state, result, dimension="manager")
    debate = updated["investment_debate_state"]
    assert updated["investment_plan"] == "Recommendation: BUY"
    assert debate["judge_decision"] == "Recommendation: BUY"
    assert debate["research_status"] == "full"
    assert debate["research_mode"] == "debate"
    assert debate["covered_dimensions"] == ["bull", "bear", "manager"]
    assert debate["manager_confidence"] == 1.0


def test_bear_guard_exception_returns_degraded_argument(monkeypatch):
    def broken_bear(_llm, _memory):
        def node(_state):
            raise ConnectionError("downstream unavailable")

        return node

    monkeypatch.setattr(graph_setup_module, "create_bear_researcher", broken_bear)
    setup = _setup()
    wrapped = setup._guard_research_node("Bear Researcher", None, None)
    state = {
        "investment_debate_state": {
            "history": "Bull Analyst: case",
            "bull_history": "Bull Analyst: case",
            "bear_history": "",
            "current_response": "Bull Analyst: case",
            "judge_decision": "",
            "count": 1,
            "research_status": "full",
            "research_mode": "debate",
            "timed_out_nodes": [],
            "degraded_reason": None,
            "covered_dimensions": ["bull"],
            "manager_confidence": None,
        }
    }

    result = wrapped(state)

    debate = result["investment_debate_state"]
    assert debate["research_status"] == "degraded"
    assert debate["research_mode"] == "degraded_synthesis"
    assert debate["degraded_reason"] == "bear_researcher_connectionerror"
    assert debate["timed_out_nodes"] == []
    assert debate["count"] == 2
    assert debate["current_response"].startswith(
        "Bear Analyst: [DEGRADED] Bear Researcher unavailable (bear_researcher_connectionerror)."
    )
    assert debate["history"].startswith("Bull Analyst: case\nBear Analyst: [DEGRADED]")
    assert debate["bear_history"].startswith("\nBear Analyst: [DEGRADED]")


def test_guard_timeout_returns_without_waiting_for_node_completion(monkeypatch):
    def slow_bull(_llm, _memory):
        def node(_state):
            time.sleep(0.2)
            return {"investment_debate_state": {"history": "", "bull_history": "", "bear_history": "", "current_response": "", "judge_decision": "", "count": 1}}
        return node

    monkeypatch.setattr(graph_setup_module, "create_bull_researcher", slow_bull)
    setup = _setup()
    wrapped = setup._guard_research_node("Bull Researcher", None, None)
    state = {
        "investment_debate_state": {
            "history": "",
            "bull_history": "",
            "bear_history": "",
            "current_response": "",
            "judge_decision": "",
            "count": 0,
            "research_status": "full",
            "research_mode": "debate",
            "timed_out_nodes": [],
            "degraded_reason": None,
            "covered_dimensions": [],
            "manager_confidence": None,
        }
    }

    started = time.monotonic()
    result = wrapped(state)
    elapsed = time.monotonic() - started

    assert elapsed < 0.1
    debate = result["investment_debate_state"]
    assert debate["research_status"] == "degraded"
    assert debate["research_mode"] == "degraded_synthesis"
    assert debate["timed_out_nodes"] == ["Bull Researcher"]
