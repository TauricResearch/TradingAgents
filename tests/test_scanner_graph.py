"""Tests for the MacroScannerGraph and scanner setup."""


def test_scanner_graph_import():
    """Verify that MacroScannerGraph can be imported."""
    from tradingagents.graph.scanner_graph import MacroScannerGraph

    assert MacroScannerGraph is not None


def test_scanner_graph_instantiates():
    """Verify that MacroScannerGraph can be instantiated with default config."""
    from tradingagents.graph.scanner_graph import MacroScannerGraph

    scanner = MacroScannerGraph()
    assert scanner is not None
    assert scanner.graph is not None


def test_scanner_setup_compiles_graph():
    """Verify that ScannerGraphSetup produces a compiled graph."""
    from tradingagents.graph.scanner_setup import ScannerGraphSetup

    setup = ScannerGraphSetup()
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
