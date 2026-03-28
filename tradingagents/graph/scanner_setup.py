"""Setup for the scanner workflow graph."""

from langgraph.graph import StateGraph, START, END

from tradingagents.agents.utils.scanner_states import ScannerState


class ScannerGraphSetup:
    """Sets up the scanner graph with LLM agent nodes.

    Phase 1a (parallel from START):
        geopolitical_scanner, market_movers_scanner, sector_scanner
    Phase 1b (sequential after sector_scanner):
        factor_alignment_scanner, smart_money_scanner — bounded global follow-ons
        that use sector rotation context
    Phase 1c:
        drift_scanner — runs after both sector and market-movers data exist
    Phase 2: industry_deep_dive (fan-in from all Phase 1 nodes)
    Phase 3: macro_synthesis -> END
    """

    def __init__(self, agents: dict) -> None:
        """
        Args:
            agents: Dict mapping node names to agent node functions:
                - geopolitical_scanner
                - market_movers_scanner
                - sector_scanner
                - factor_alignment_scanner
                - drift_scanner
                - smart_money_scanner
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

        # Phase 1a: parallel fan-out from START
        workflow.add_edge(START, "geopolitical_scanner")
        workflow.add_edge(START, "market_movers_scanner")
        workflow.add_edge(START, "sector_scanner")

        # Phase 1b: bounded global follow-ons that require sector context
        workflow.add_edge("sector_scanner", "factor_alignment_scanner")
        workflow.add_edge("sector_scanner", "smart_money_scanner")
        workflow.add_edge("sector_scanner", "drift_scanner")
        workflow.add_edge("market_movers_scanner", "drift_scanner")

        # Fan-in: all Phase 1 nodes must complete before Phase 2
        workflow.add_edge("geopolitical_scanner", "industry_deep_dive")
        workflow.add_edge("market_movers_scanner", "industry_deep_dive")
        workflow.add_edge("factor_alignment_scanner", "industry_deep_dive")
        workflow.add_edge("drift_scanner", "industry_deep_dive")
        workflow.add_edge("smart_money_scanner", "industry_deep_dive")

        # Phase 2 -> Phase 3 -> END
        workflow.add_edge("industry_deep_dive", "macro_synthesis")
        workflow.add_edge("macro_synthesis", END)

        return workflow.compile()
