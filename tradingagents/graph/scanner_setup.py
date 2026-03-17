"""Setup for the scanner workflow graph."""

from langgraph.graph import StateGraph, START, END

from tradingagents.agents.utils.scanner_states import ScannerState


class ScannerGraphSetup:
    """Sets up the 3-phase scanner graph with LLM agent nodes.

    Phase 1: geopolitical_scanner, market_movers_scanner, sector_scanner (parallel fan-out)
    Phase 2: industry_deep_dive (fan-in from all three Phase 1 nodes)
    Phase 3: macro_synthesis -> END
    """

    def __init__(self, agents: dict) -> None:
        """
        Args:
            agents: Dict mapping node names to agent node functions:
                - geopolitical_scanner
                - market_movers_scanner
                - sector_scanner
                - industry_deep_dive
                - macro_synthesis
        """
        self.agents = agents

    def setup_graph(self):
        """Build and compile the scanner workflow graph.

        Returns:
            A compiled LangGraph graph ready to invoke.
        """
        workflow = StateGraph(ScannerState)

        for name, node_fn in self.agents.items():
            workflow.add_node(name, node_fn)

        # Phase 1: parallel fan-out from START
        workflow.add_edge(START, "geopolitical_scanner")
        workflow.add_edge(START, "market_movers_scanner")
        workflow.add_edge(START, "sector_scanner")

        # Fan-in: all three Phase 1 nodes must complete before Phase 2
        workflow.add_edge("geopolitical_scanner", "industry_deep_dive")
        workflow.add_edge("market_movers_scanner", "industry_deep_dive")
        workflow.add_edge("sector_scanner", "industry_deep_dive")

        # Phase 2 -> Phase 3 -> END
        workflow.add_edge("industry_deep_dive", "macro_synthesis")
        workflow.add_edge("macro_synthesis", END)

        return workflow.compile()
