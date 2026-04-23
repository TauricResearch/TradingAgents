"""Tests for scanner_graph_context_text field in AgentState and Propagator."""
from tradingagents.graph.propagation import Propagator


def _make_propagator():
    return Propagator(max_recur_limit=100)


def test_create_initial_state_default_scanner_context():
    """scanner_graph_context_text defaults to empty string."""
    p = _make_propagator()
    state = p.create_initial_state(
        company_name="AAPL",
        trade_date="2026-04-16",
        run_id="TESTRUN",
    )
    assert "scanner_graph_context_text" in state
    assert state["scanner_graph_context_text"] == ""


def test_create_initial_state_with_scanner_context():
    """scanner_graph_context_text is stored when provided."""
    p = _make_propagator()
    ctx = "## Global Market Regime\n- Risk-On\n\n## Ticker Graph Context: ON\n- ON belongs to Technology."
    state = p.create_initial_state(
        company_name="ON",
        trade_date="2026-04-16",
        run_id="TESTRUN",
        scanner_graph_context_text=ctx,
    )
    assert state["scanner_graph_context_text"] == ctx


def test_agent_state_has_scanner_context_field():
    """AgentState TypedDict must include scanner_graph_context_text."""
    from tradingagents.agents.utils.agent_states import AgentState
    # AgentState is a TypedDict — check field is in __annotations__
    annotations = {}
    for cls in type(AgentState).__mro__:
        annotations.update(getattr(cls, "__annotations__", {}))
    annotations.update(getattr(AgentState, "__annotations__", {}))
    assert "scanner_graph_context_text" in annotations


def test_scanner_context_packet_still_present():
    """scanner_context_packet must remain (used by operator resume paths)."""
    from tradingagents.agents.utils.agent_states import AgentState
    annotations = {}
    for cls in type(AgentState).__mro__:
        annotations.update(getattr(cls, "__annotations__", {}))
    annotations.update(getattr(AgentState, "__annotations__", {}))
    assert "scanner_context_packet" in annotations


def test_create_initial_state_scanner_context_does_not_overwrite_other_fields():
    """Adding scanner_graph_context_text must not displace any existing field."""
    p = _make_propagator()
    state = p.create_initial_state(
        company_name="NVDA",
        trade_date="2026-04-16",
        run_id="RUN1",
        scanner_graph_context_text="some context",
    )
    # Essential existing fields must still be present
    assert "run_id" in state
    assert "company_of_interest" in state
    assert "scanner_context_packet" in state
    assert state["run_id"] == "RUN1"
    assert state["company_of_interest"] == "NVDA"
