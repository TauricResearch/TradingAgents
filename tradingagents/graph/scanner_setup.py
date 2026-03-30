"""Setup for the scanner workflow graph."""

from langgraph.graph import StateGraph, START, END

from tradingagents.agents.utils.scanner_states import ScannerState


SCANNER_START_NODES: tuple[str, ...] = (
    "gatekeeper_scanner",
    "geopolitical_scanner",
    "market_movers_scanner",
    "sector_scanner",
)

SCANNER_PREDECESSORS: dict[str, tuple[str, ...]] = {
    "factor_alignment_scanner": ("sector_scanner",),
    "smart_money_scanner": ("sector_scanner",),
    "drift_scanner": ("sector_scanner", "market_movers_scanner", "gatekeeper_scanner"),
    "industry_deep_dive": (
        "gatekeeper_scanner",
        "geopolitical_scanner",
        "market_movers_scanner",
        "factor_alignment_scanner",
        "drift_scanner",
        "smart_money_scanner",
    ),
    "macro_synthesis": ("industry_deep_dive",),
}

SCANNER_NODES: tuple[str, ...] = SCANNER_START_NODES + tuple(SCANNER_PREDECESSORS.keys())


class ScannerGraphSetup:
    """Sets up the scanner graph with LLM agent nodes.

    Phase 1a (parallel from START):
        gatekeeper_scanner, geopolitical_scanner, market_movers_scanner, sector_scanner
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
                - gatekeeper_scanner
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

        for node in SCANNER_START_NODES:
            workflow.add_edge(START, node)

        for node, predecessors in SCANNER_PREDECESSORS.items():
            if len(predecessors) == 1:
                workflow.add_edge(predecessors[0], node)
            else:
                workflow.add_edge(list(predecessors), node)

        workflow.add_edge("macro_synthesis", END)

        return workflow.compile()

    def setup_graph_from(self, start_node: str):
        """Build and compile a partial scanner workflow from *start_node* onward.

        The returned graph starts at ``start_node`` and keeps only downstream
        nodes. Missing predecessor data must already be present in the seeded
        state supplied by the caller.
        """
        if start_node not in self.agents:
            raise ValueError(f"Unknown scanner node: {start_node}")

        adjacency: dict[str, set[str]] = {}
        for node, predecessors in SCANNER_PREDECESSORS.items():
            for predecessor in predecessors:
                adjacency.setdefault(predecessor, set()).add(node)

        reachable = {start_node}
        stack = [start_node]
        while stack:
            node = stack.pop()
            for child in adjacency.get(node, set()):
                if child not in reachable:
                    reachable.add(child)
                    stack.append(child)

        workflow = StateGraph(ScannerState)
        for name, node_fn in self.agents.items():
            if name in reachable:
                workflow.add_node(name, node_fn)

        workflow.add_edge(START, start_node)

        for node, predecessors in SCANNER_PREDECESSORS.items():
            if node not in reachable:
                continue
            live_predecessors = [pred for pred in predecessors if pred in reachable]
            if not live_predecessors:
                continue
            if len(live_predecessors) == 1:
                workflow.add_edge(live_predecessors[0], node)
            else:
                workflow.add_edge(live_predecessors, node)

        if "macro_synthesis" in reachable:
            workflow.add_edge("macro_synthesis", END)

        return workflow.compile()
