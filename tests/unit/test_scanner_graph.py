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
        "gatekeeper_scanner": MagicMock(),
        "geopolitical_scanner": MagicMock(),
        "market_movers_scanner": MagicMock(),
        "sector_scanner": MagicMock(),
        "factor_alignment_scanner": MagicMock(),
        "drift_scanner": MagicMock(),
        "smart_money_scanner": MagicMock(),
        "industry_deep_dive": MagicMock(),
        "macro_synthesis": MagicMock(),
        "summarize_gatekeeper": MagicMock(),
        "summarize_geopolitical": MagicMock(),
        "summarize_market_movers": MagicMock(),
        "summarize_sector": MagicMock(),
        "summarize_factor_alignment": MagicMock(),
        "summarize_drift": MagicMock(),
        "summarize_smart_money": MagicMock(),
        "summarize_industry_deep_dive": MagicMock(),
    }
    setup = ScannerGraphSetup(mock_agents)
    graph = setup.setup_graph()
    assert graph is not None


def test_scanner_setup_runs_fan_in_nodes_once():
    """Barrier edges should prevent duplicate drift/deep-dive executions."""
    from tradingagents.graph.scanner_setup import ScannerGraphSetup

    counts: dict[str, int] = {}
    report_fields = {
        "gatekeeper_scanner": "gatekeeper_universe_report",
        "geopolitical_scanner": "geopolitical_report",
        "market_movers_scanner": "market_movers_report",
        "sector_scanner": "sector_performance_report",
        "factor_alignment_scanner": "factor_alignment_report",
        "drift_scanner": "drift_opportunities_report",
        "smart_money_scanner": "smart_money_report",
        "industry_deep_dive": "industry_deep_dive_report",
        "macro_synthesis": "macro_scan_summary",
        "summarize_gatekeeper": "gatekeeper_summary",
        "summarize_geopolitical": "geopolitical_summary",
        "summarize_market_movers": "market_movers_summary",
        "summarize_sector": "sector_summary",
        "summarize_factor_alignment": "factor_alignment_summary",
        "summarize_drift": "drift_opportunities_summary",
        "summarize_smart_money": "smart_money_summary",
        "summarize_industry_deep_dive": "industry_deep_dive_summary",
    }

    def make_node(name: str):
        field = report_fields[name]

        def _node(_state):
            counts[name] = counts.get(name, 0) + 1
            return {"messages": [], "sender": name, field: name}

        return _node

    setup = ScannerGraphSetup({name: make_node(name) for name in report_fields})
    graph = setup.setup_graph()

    result = graph.invoke(
        {
            "scan_date": "2026-03-30",
            "messages": [],
            "gatekeeper_universe_report": "",
            "geopolitical_report": "",
            "market_movers_report": "",
            "sector_performance_report": "",
            "factor_alignment_report": "",
            "drift_opportunities_report": "",
            "smart_money_report": "",
            "industry_deep_dive_report": "",
            "macro_scan_summary": "",
            "gatekeeper_summary": "",
            "geopolitical_summary": "",
            "market_movers_summary": "",
            "sector_summary": "",
            "factor_alignment_summary": "",
            "drift_opportunities_summary": "",
            "smart_money_summary": "",
            "industry_deep_dive_summary": "",
            "sender": "",
        }
    )

    assert all(counts.get(name) == 1 for name in report_fields)
    assert result["macro_scan_summary"] == "macro_synthesis"


def test_scanner_partial_graph_runs_selected_node_only_when_terminal():
    """Partial scanner reruns should allow starting directly at macro_synthesis."""
    from tradingagents.graph.scanner_setup import ScannerGraphSetup

    counts: dict[str, int] = {}

    def make_node(name: str):
        def _node(_state):
            counts[name] = counts.get(name, 0) + 1
            return {"messages": [], "sender": name, "macro_scan_summary": name}

        return _node

    mock_agents = {
        "gatekeeper_scanner": make_node("gatekeeper_scanner"),
        "geopolitical_scanner": make_node("geopolitical_scanner"),
        "market_movers_scanner": make_node("market_movers_scanner"),
        "sector_scanner": make_node("sector_scanner"),
        "factor_alignment_scanner": make_node("factor_alignment_scanner"),
        "drift_scanner": make_node("drift_scanner"),
        "smart_money_scanner": make_node("smart_money_scanner"),
        "industry_deep_dive": make_node("industry_deep_dive"),
        "macro_synthesis": make_node("macro_synthesis"),
        "summarize_gatekeeper": make_node("summarize_gatekeeper"),
        "summarize_geopolitical": make_node("summarize_geopolitical"),
        "summarize_market_movers": make_node("summarize_market_movers"),
        "summarize_sector": make_node("summarize_sector"),
        "summarize_factor_alignment": make_node("summarize_factor_alignment"),
        "summarize_drift": make_node("summarize_drift"),
        "summarize_smart_money": make_node("summarize_smart_money"),
        "summarize_industry_deep_dive": make_node("summarize_industry_deep_dive"),
    }
    setup = ScannerGraphSetup(mock_agents)
    graph = setup.setup_graph_from("macro_synthesis")

    result = graph.invoke(
        {
            "scan_date": "2026-03-30",
            "messages": [],
            "gatekeeper_universe_report": "seeded",
            "geopolitical_report": "seeded",
            "market_movers_report": "seeded",
            "sector_performance_report": "seeded",
            "factor_alignment_report": "seeded",
            "drift_opportunities_report": "seeded",
            "smart_money_report": "seeded",
            "industry_deep_dive_report": "seeded",
            "macro_scan_summary": "",
            "sender": "",
        }
    )

    assert counts == {"macro_synthesis": 1}
    assert result["macro_scan_summary"] == "macro_synthesis"


def test_scanner_states_import():
    """Verify that ScannerState can be imported."""
    from tradingagents.agents.utils.scanner_states import ScannerState

    assert ScannerState is not None


def test_scanner_state_preserves_scan_date_across_fan_in():
    """scan_date is required by downstream fan-in nodes such as industry_deep_dive."""
    from typing import Annotated, get_args, get_origin, get_type_hints

    from tradingagents.agents.utils.scanner_states import ScannerState, _last_value

    hints = get_type_hints(ScannerState, include_extras=True)
    scan_date_hint = hints["scan_date"]

    assert get_origin(scan_date_hint) is Annotated
    assert get_args(scan_date_hint)[1] is _last_value


if __name__ == "__main__":
    test_scanner_graph_import()
    test_scanner_graph_instantiates()
    test_scanner_setup_compiles_graph()
    test_scanner_states_import()
    print("All scanner graph tests passed.")
