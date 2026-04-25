"""Setup for the scanner workflow graph."""

from typing import Any

from langgraph.graph import END, START, StateGraph

from tradingagents.agents.utils.scanner_states import ScannerState

SCANNER_START_NODES: tuple[str, ...] = (
    "gatekeeper_scanner",
    "geopolitical_scanner",
    "market_movers_scanner",
    "sector_scanner",
)

SCANNER_PREDECESSORS: dict[str, tuple[str, ...]] = {
    # Summaries for Phase 1a
    "summarize_gatekeeper": ("gatekeeper_scanner",),
    "summarize_geopolitical": ("geopolitical_scanner",),
    "summarize_market_movers": ("market_movers_scanner",),
    "summarize_sector": ("sector_scanner",),
    # Phase 1b/c
    "factor_alignment_scanner": ("summarize_sector",),
    "smart_money_scanner": ("summarize_sector",),
    "drift_scanner": ("summarize_sector", "summarize_market_movers", "summarize_gatekeeper"),
    # Summaries for Phase 1b/c
    "summarize_factor_alignment": ("factor_alignment_scanner",),
    "summarize_smart_money": ("smart_money_scanner",),
    "summarize_drift": ("drift_scanner",),
    # Phase 2
    "industry_deep_dive": (
        "summarize_gatekeeper",
        "summarize_geopolitical",
        "summarize_market_movers",
        "summarize_factor_alignment",
        "summarize_drift",
        "summarize_smart_money",
    ),
    "summarize_industry_deep_dive": ("industry_deep_dive",),
    # Phase 3
    "macro_synthesis": (
        "summarize_gatekeeper",
        "summarize_geopolitical",
        "summarize_market_movers",
        "summarize_sector",
        "summarize_factor_alignment",
        "summarize_drift",
        "summarize_smart_money",
        "summarize_industry_deep_dive",
    ),
}

SCANNER_NODES: tuple[str, ...] = SCANNER_START_NODES + tuple(SCANNER_PREDECESSORS.keys())


def get_scanner_descendants(start_node: str) -> frozenset[str]:
    """Return the node and all its downstream descendants in the scanner graph."""
    if start_node not in SCANNER_NODES:
        return frozenset()

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

    return frozenset(reachable)


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

    def setup_graph(self) -> Any:
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

    def setup_graph_from(self, start_node: str) -> Any:
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
