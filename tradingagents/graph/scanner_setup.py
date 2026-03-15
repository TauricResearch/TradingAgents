# tradingagents/graph/scanner_setup.py
from langgraph.graph import StateGraph, START, END

from tradingagents.agents.utils.scanner_states import ScannerState
from tradingagents.dataflows.interface import route_to_vendor


def geopolitical_scanner_node(state: ScannerState) -> dict:
    """Phase 1: Fetch geopolitical and macro news."""
    result = route_to_vendor("get_topic_news", "geopolitics global economy", 10)
    return {"geopolitical_report": result}


def market_movers_scanner_node(state: ScannerState) -> dict:
    """Phase 1: Fetch market movers and index performance."""
    movers = route_to_vendor("get_market_movers", "day_gainers")
    indices = route_to_vendor("get_market_indices")
    return {"market_movers_report": movers + "\n\n" + indices}


def sector_scanner_node(state: ScannerState) -> dict:
    """Phase 1: Fetch sector performance overview."""
    result = route_to_vendor("get_sector_performance")
    return {"sector_performance_report": result}


def industry_deep_dive_node(state: ScannerState) -> dict:
    """Phase 2: Drill down into the technology sector as a representative example."""
    result = route_to_vendor("get_industry_performance", "technology")
    return {"industry_deep_dive_report": result}


def macro_synthesis_node(state: ScannerState) -> dict:
    """Phase 3: Combine all scanner outputs into a final summary."""
    parts = [
        state.get("geopolitical_report", ""),
        state.get("market_movers_report", ""),
        state.get("sector_performance_report", ""),
        state.get("industry_deep_dive_report", ""),
    ]
    summary = "\n\n---\n\n".join(p for p in parts if p)
    return {"macro_scan_summary": summary}


class ScannerGraphSetup:
    """Handles the setup and configuration of the scanner graph."""

    def setup_graph(self):
        """Set up and compile the scanner workflow graph."""
        workflow = StateGraph(ScannerState)

        # Phase 1: parallel scanners
        workflow.add_node("geopolitical_scanner", geopolitical_scanner_node)
        workflow.add_node("market_movers_scanner", market_movers_scanner_node)
        workflow.add_node("sector_scanner", sector_scanner_node)

        # Phase 2: industry deep dive
        workflow.add_node("industry_deep_dive", industry_deep_dive_node)

        # Phase 3: macro synthesis
        workflow.add_node("macro_synthesis", macro_synthesis_node)

        # Fan-out from START to 3 parallel scanners
        workflow.add_edge(START, "geopolitical_scanner")
        workflow.add_edge(START, "market_movers_scanner")
        workflow.add_edge(START, "sector_scanner")

        # Fan-in: LangGraph's StateGraph guarantees that industry_deep_dive
        # only executes after ALL three predecessor nodes have completed and
        # their state updates have been merged.
        workflow.add_edge("geopolitical_scanner", "industry_deep_dive")
        workflow.add_edge("market_movers_scanner", "industry_deep_dive")
        workflow.add_edge("sector_scanner", "industry_deep_dive")

        # Sequential: deep dive → synthesis → end
        workflow.add_edge("industry_deep_dive", "macro_synthesis")
        workflow.add_edge("macro_synthesis", END)

        return workflow.compile()
