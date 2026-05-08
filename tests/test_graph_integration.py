"""Integration smoke test: exercises the full compile+propagate path.

Uses mock LLMs so no API calls are made.  The test verifies that:

- The graph compiles without errors (node wiring is correct).
- ``propagate()`` returns a ``(final_state, signal)`` tuple.
- ``final_state`` contains all expected top-level keys.
- The signal is one of the five canonical rating strings.
- The memory log receives a pending entry after the run.

This catches graph wiring regressions (mismatched node names, missing state
fields, broken fan-out/fan-in edges) that unit tests on isolated components
cannot detect.
"""

from __future__ import annotations

import functools
from unittest.mock import MagicMock, patch

import pytest

from tradingagents.agents.schemas import (
    PortfolioDecision,
    PortfolioRating,
    ResearchPlan,
    TraderAction,
    TraderProposal,
)
from tradingagents.agents.utils.memory import TradingMemoryLog
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.propagation import Propagator
from tradingagents.graph.trading_graph import TradingAgentsGraph


# ---------------------------------------------------------------------------
# Mock LLM — no API calls
# ---------------------------------------------------------------------------

class _MockLLM:
    """Minimal LLM stub that handles every calling pattern in the graph.

    - ``bind_tools()``: returns a stub whose ``invoke()`` returns an AIMessage
      with no tool_calls so the analyst tool-loop exits immediately.
    - ``invoke()``: returns a stub message for researcher/debater nodes.
    - ``with_structured_output(schema)``: returns a stub that returns a valid
      Pydantic instance for each of the three decision-making schemas.
    """

    def bind_tools(self, tools):
        from langchain_core.messages import AIMessage
        stub = MagicMock()
        stub.invoke.return_value = AIMessage(
            content="Mock analyst report — no real data.", tool_calls=[]
        )
        return stub

    def invoke(self, prompt):
        from langchain_core.messages import AIMessage
        return AIMessage(content="Bull Analyst: mock debate argument.")

    def with_structured_output(self, schema, **kwargs):
        stub = MagicMock()
        name = getattr(schema, "__name__", "")

        if name == "ResearchPlan":
            stub.invoke.return_value = ResearchPlan(
                recommendation=PortfolioRating.HOLD,
                rationale="Balanced mock arguments from both sides.",
                strategic_actions="Maintain current position; revisit next quarter.",
            )
        elif name == "TraderProposal":
            stub.invoke.return_value = TraderProposal(
                action=TraderAction.HOLD,
                reasoning="Waiting for a clearer directional signal.",
            )
        elif name == "PortfolioDecision":
            stub.invoke.return_value = PortfolioDecision(
                rating=PortfolioRating.HOLD,
                executive_summary="Hold the position; no catalyst to act.",
                investment_thesis="Evidence is balanced; neither bull nor bear side dominated.",
            )
        else:
            # Unknown schema — return a generic mock (fail loudly if accessed).
            stub.invoke.side_effect = ValueError(f"Unexpected schema: {name}")
        return stub


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_graph(tmp_path):
    """Real TradingAgentsGraph with mock LLMs injected via patch."""
    config = {
        **DEFAULT_CONFIG,
        "results_dir": str(tmp_path / "results"),
        "data_cache_dir": str(tmp_path / "cache"),
        "memory_log_path": str(tmp_path / "mem.md"),
        "checkpoint_enabled": False,
    }

    llm = _MockLLM()
    mock_client = MagicMock()
    mock_client.get_llm.return_value = llm

    with patch(
        "tradingagents.graph.trading_graph.create_llm_client",
        return_value=mock_client,
    ):
        graph = TradingAgentsGraph(selected_analysts=["market", "news"], config=config)

    return graph


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.smoke
def test_graph_compiles(mock_graph):
    """The graph object is created and the compiled workflow is not None."""
    assert mock_graph.graph is not None
    assert mock_graph.workflow is not None


@pytest.mark.smoke
def test_propagate_returns_tuple(mock_graph, tmp_path):
    """propagate() returns a (dict, str) tuple without raising."""
    # Patch _fetch_returns so no yfinance calls are made for pending entries.
    mock_graph._fetch_returns = MagicMock(return_value=(None, None, None))

    final_state, signal = mock_graph.propagate("NVDA", "2026-01-10")

    assert isinstance(final_state, dict), "final_state should be a dict"
    assert isinstance(signal, str), "signal should be a string"


@pytest.mark.smoke
def test_propagate_signal_is_valid_rating(mock_graph):
    """The signal extracted from the PM decision is one of the five canonical values."""
    mock_graph._fetch_returns = MagicMock(return_value=(None, None, None))
    _final_state, signal = mock_graph.propagate("NVDA", "2026-01-10")
    assert signal in ("Buy", "Overweight", "Hold", "Underweight", "Sell")


@pytest.mark.smoke
def test_propagate_final_state_has_required_keys(mock_graph):
    """final_state carries the keys that downstream consumers depend on."""
    mock_graph._fetch_returns = MagicMock(return_value=(None, None, None))
    final_state, _signal = mock_graph.propagate("NVDA", "2026-01-10")

    required = {
        "final_trade_decision",
        "investment_plan",
        "trader_investment_plan",
        "analyst_reports",
        "company_of_interest",
    }
    missing = required - set(final_state.keys())
    assert not missing, f"final_state missing keys: {missing}"


@pytest.mark.smoke
def test_propagate_writes_memory_log_entry(mock_graph, tmp_path):
    """A pending log entry is created in the memory log after propagate()."""
    mock_graph._fetch_returns = MagicMock(return_value=(None, None, None))
    mock_graph.propagate("NVDA", "2026-01-10")

    entries = mock_graph.memory_log.load_entries()
    assert len(entries) == 1
    assert entries[0]["ticker"] == "NVDA"
    assert entries[0]["date"] == "2026-01-10"
    assert entries[0]["pending"] is True


@pytest.mark.smoke
def test_propagate_analyst_reports_populated(mock_graph):
    """analyst_reports dict has an entry for each selected analyst after the run."""
    mock_graph._fetch_returns = MagicMock(return_value=(None, None, None))
    final_state, _ = mock_graph.propagate("NVDA", "2026-01-10")

    reports = final_state.get("analyst_reports", {})
    # mock_graph was created with selected_analysts=["market", "news"]
    assert "market" in reports, "market analyst report missing"
    assert "news" in reports, "news analyst report missing"


@pytest.mark.smoke
def test_graph_wiring_all_analysts(tmp_path):
    """Graph compiles and propagates with all four analysts selected."""
    config = {
        **DEFAULT_CONFIG,
        "results_dir": str(tmp_path / "results"),
        "data_cache_dir": str(tmp_path / "cache"),
        "memory_log_path": str(tmp_path / "mem.md"),
        "checkpoint_enabled": False,
    }

    llm = _MockLLM()
    mock_client = MagicMock()
    mock_client.get_llm.return_value = llm

    with patch(
        "tradingagents.graph.trading_graph.create_llm_client",
        return_value=mock_client,
    ):
        graph = TradingAgentsGraph(
            selected_analysts=["market", "social", "news", "fundamentals"],
            config=config,
        )

    graph._fetch_returns = MagicMock(return_value=(None, None, None))
    final_state, signal = graph.propagate("AAPL", "2026-02-01")

    assert signal in ("Buy", "Overweight", "Hold", "Underweight", "Sell")
    reports = final_state.get("analyst_reports", {})
    for key in ("market", "social", "news", "fundamentals"):
        assert key in reports, f"{key} analyst report missing from final_state"


@pytest.mark.smoke
def test_invalid_analyst_key_raises():
    """Unknown analyst type raises ValueError at graph construction time."""
    config = {**DEFAULT_CONFIG}
    llm = _MockLLM()
    mock_client = MagicMock()
    mock_client.get_llm.return_value = llm

    with patch(
        "tradingagents.graph.trading_graph.create_llm_client",
        return_value=mock_client,
    ):
        with pytest.raises(ValueError, match="Unknown analyst"):
            TradingAgentsGraph(selected_analysts=["markt"], config=config)
