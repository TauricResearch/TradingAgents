import pytest
from langgraph.graph import END, START, StateGraph

from tradingagents.agents.utils.agent_states import AgentState
from tradingagents.graph._consistency_guard import (
    NumericClaim,
    extract_numeric_claims,
    verify_against_fundamentals,
)


def test_extract_high_confidence_percent_claim():
    rm_text = "- EBITDA margin expanded +3.8% YoY coinciding with..."
    claims = extract_numeric_claims(rm_text)
    assert any(
        c.metric.lower().startswith("ebitda margin")
        and c.value == 3.8
        and c.unit == "%"
        and c.direction == "expansion"
        for c in claims
    )


def test_extract_bps_claim():
    rm_text = "- net leverage declined 320bps to 3.8x"
    claims = extract_numeric_claims(rm_text)
    bps = [c for c in claims if c.unit == "bps"]
    assert bps and bps[0].value == 320 and bps[0].direction == "compression"


def test_revenue_decline_extracts_decrease_not_compression():
    rm_text = "- Revenue declined 5% year-over-year"
    claims = extract_numeric_claims(rm_text)
    assert any(
        c.metric.lower() == "revenue"
        and c.value == 5
        and c.unit == "%"
        and c.direction == "decrease"
        for c in claims
    )


def test_verify_detects_sign_disagreement():
    """RM claims margin expansion; fundamentals shows compression."""
    fundamentals = "Operating margin Q4 2025: 9.3% vs Q2 2025: 12.0% - 270bps compression"
    claims = [
        NumericClaim(
            metric="EBITDA margin",
            value=3.8,
            unit="%",
            direction="expansion",
            confidence="high",
        )
    ]
    result = verify_against_fundamentals(claims, fundamentals)
    assert len(result["violations"]) == 1
    assert "expansion" in result["violations"][0].reason.lower()


def test_verify_passes_when_within_tolerance():
    fundamentals = "Operating margin compressed 270bps over 2 quarters"
    claims = [
        NumericClaim(
            metric="operating margin",
            value=270,
            unit="bps",
            direction="compression",
            confidence="high",
        )
    ]
    result = verify_against_fundamentals(claims, fundamentals)
    assert result["violations"] == []


def test_unmappable_claim_downgrades_to_flag():
    """Metric not in fundamentals -> flag-only, not a violation."""
    fundamentals = "Operating margin compressed 270bps"
    claims = [
        NumericClaim(
            metric="DCF coverage ratio",
            value=1.2,
            unit="x",
            direction=None,
            confidence="low",
        )
    ]
    result = verify_against_fundamentals(claims, fundamentals)
    assert result["violations"] == []
    assert claims[0] in result["flags"]


def test_replay_et_rm_violations():
    """ET RM from run 01KQHDVJB2R19S4D7Z7Z6DP9F7 vs fundamentals report."""
    rm_text = (
        "- EBITDA margin expanded +3.8% YoY coinciding with U.S. sovereign...\n"
        "- Free cash flow conversion improved +14.2bps quarter-over-quarter "
        "while net leverage declined 320bps to 3.8x"
    )
    fundamentals = (
        "Operating margins peaked at 12.0% in Q2 2025 and have since declined to "
        "9.3% in Q4 2025, a 270bps compression. "
        "Free cash flow turned negative in Q4 2025 (-$225M). "
        "Total debt increased by $6.119B in Q4 2025 (+9.6% QoQ)."
    )
    claims = extract_numeric_claims(rm_text)
    result = verify_against_fundamentals(claims, fundamentals)
    violation_metrics = {violation.claim.metric.lower() for violation in result["violations"]}
    assert any("margin" in metric for metric in violation_metrics)
    assert any("leverage" in metric or "debt" in metric for metric in violation_metrics)


def test_guard_node_passes_clean_rm_output():
    """Clean RM output -> no violations, no re-prompt, sender set."""
    from tradingagents.graph.setup import GraphSetup

    node = GraphSetup._make_rm_consistency_guard_node()
    state = {
        "investment_plan": "- Operating margin compressed 270bps over 2 quarters",
        "fundamentals_report": "Operating margins compressed 270bps from Q2 to Q4 2025.",
        "_rm_consistency_attempt": 0,
    }
    result = node(state)
    assert result["rm_consistency_status"] == "ok"
    assert result["sender"] == "rm_consistency_guard"
    assert result["consistency_violations"] == []
    assert "_rm_consistency_attempt" not in result


def test_guard_node_raises_after_second_offense():
    """Second-pass RM still violates -> hard fail."""
    from tradingagents.graph.setup import GraphSetup

    node = GraphSetup._make_rm_consistency_guard_node()
    state = {
        "investment_plan": "- EBITDA margin expanded +3.8% YoY",
        "fundamentals_report": "Operating margin compressed 270bps.",
        "_rm_consistency_attempt": 1,
    }
    with pytest.raises(ValueError, match=r"unresolved.*violations"):
        node(state)


def test_guard_node_routes_to_reprompt_on_first_offense():
    """First-pass RM violates -> return signal to re-prompt RM."""
    from tradingagents.graph.setup import GraphSetup

    node = GraphSetup._make_rm_consistency_guard_node()
    state = {
        "investment_plan": "- EBITDA margin expanded +3.8% YoY",
        "fundamentals_report": "Operating margin compressed 270bps.",
        "_rm_consistency_attempt": 0,
    }
    result = node(state)
    assert result.get("rm_consistency_status") == "reprompt"
    assert "consistency_violations" in result
    assert result["_rm_consistency_attempt"] == 1


def test_guard_graph_state_persists_reprompt_context_to_next_node():
    """Guard re-prompt payload survives conditional routing into the next node."""
    from tradingagents.graph.setup import GraphSetup

    def probe_node(state: AgentState) -> dict:
        assert state["rm_consistency_status"] == "reprompt"
        assert state["consistency_violations"]
        assert state["_rm_consistency_attempt"] == 1
        return {"sender": "probe"}

    workflow = StateGraph(AgentState)
    workflow.add_node("Guard", GraphSetup._make_rm_consistency_guard_node())
    workflow.add_node("Probe", probe_node)
    workflow.add_edge(START, "Guard")
    workflow.add_conditional_edges(
        "Guard",
        lambda state: "Probe" if state.get("rm_consistency_status") == "reprompt" else END,
        {"Probe": "Probe", END: END},
    )
    workflow.add_edge("Probe", END)
    graph = workflow.compile()

    graph.invoke(
        {
            "investment_plan": "- EBITDA margin expanded +3.8% YoY",
            "fundamentals_report": "Operating margin compressed 270bps.",
            "_rm_consistency_attempt": 0,
        }
    )


def test_guard_graph_state_clears_stale_violations_after_clean_pass():
    """Successful corrective pass clears prior violation payload before downstream nodes."""
    from tradingagents.graph.setup import GraphSetup

    def probe_node(state: AgentState) -> dict:
        assert state["rm_consistency_status"] == "ok"
        assert state["consistency_violations"] == []
        assert state["_rm_consistency_attempt"] == 1
        return {"sender": "probe"}

    workflow = StateGraph(AgentState)
    workflow.add_node("Guard", GraphSetup._make_rm_consistency_guard_node())
    workflow.add_node("Probe", probe_node)
    workflow.add_edge(START, "Guard")
    workflow.add_edge("Guard", "Probe")
    workflow.add_edge("Probe", END)
    graph = workflow.compile()

    graph.invoke(
        {
            "investment_plan": "- Operating margin compressed 270bps over 2 quarters",
            "fundamentals_report": "Operating margin compressed 270bps.",
            "consistency_violations": [{"metric": "EBITDA margin", "reason": "stale"}],
            "_rm_consistency_attempt": 1,
        }
    )
