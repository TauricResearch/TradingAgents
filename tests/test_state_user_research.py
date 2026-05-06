def test_create_initial_state_includes_user_research_default_empty():
    from tradingagents.graph.propagation import Propagator
    p = Propagator()
    s = p.create_initial_state("AAPL", "2026-05-06")
    assert s["user_research_report"] == ""


def test_create_initial_state_passes_through_user_research():
    from tradingagents.graph.propagation import Propagator
    p = Propagator()
    s = p.create_initial_state(
        "AAPL", "2026-05-06",
        user_research="## Goldman note\nThesis: ..."
    )
    assert "Goldman" in s["user_research_report"]
