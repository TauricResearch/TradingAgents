"""Tests for ScannerGraph and ScannerGraphSetup."""

from unittest.mock import MagicMock, patch


def test_scanner_graph_import():
    """Verify that ScannerGraph can be imported.

    Root cause of previous failure: test imported 'MacroScannerGraph' which was
    renamed to 'ScannerGraph'.
    """
    from tradingagents.graph.scanner_graph import ScannerGraph

    assert ScannerGraph is not None


def test_scanner_graph_instantiates():
    """Verify that ScannerGraph can be instantiated with default config.

    _create_llm is mocked to avoid real API key / network requirements during
    unit testing.  The mock LLM is accepted by the agent factory functions
    (they return closures and never call the LLM at construction time), so the
    LangGraph compilation still exercises real graph wiring logic.
    """
    from tradingagents.graph.scanner_graph import ScannerGraph

    with patch.object(ScannerGraph, "_create_llm", return_value=MagicMock()):
        scanner = ScannerGraph()

    assert scanner is not None
    assert scanner.graph is not None


def test_scanner_setup_compiles_graph():
    """Verify that ScannerGraphSetup produces a compiled graph.

    Root cause of previous failure: ScannerGraphSetup.__init__() requires an
    'agents' dict argument.  Provide mock agent node functions so that the
    graph wiring and compilation logic is exercised without real LLMs.
    """
    from tradingagents.graph.scanner_setup import ScannerGraphSetup

    mock_agents = {
        "geopolitical_scanner": MagicMock(),
        "market_movers_scanner": MagicMock(),
        "sector_scanner": MagicMock(),
        "industry_deep_dive": MagicMock(),
        "macro_synthesis": MagicMock(),
    }
    setup = ScannerGraphSetup(mock_agents)
    graph = setup.setup_graph()
    assert graph is not None


def test_scanner_states_import():
    """Verify that ScannerState can be imported."""
    from tradingagents.agents.utils.scanner_states import ScannerState

    assert ScannerState is not None


if __name__ == "__main__":
    test_scanner_graph_import()
    test_scanner_graph_instantiates()
    test_scanner_setup_compiles_graph()
    test_scanner_states_import()
    print("All scanner graph tests passed.")
