"""JSON graph search: exact/alias ticker lookup + 1–3-hop undirected subgraph retrieval.

Traversal is undirected (edges followed in both directions).
Output edges preserve their original stored direction.
Unknown ticker raises KeyError — never returns empty silently.
"""
from __future__ import annotations

import logging
from collections import deque

from tradingagents.graph.scanner_facts.aliases import resolve_alias_for_type

_logger = logging.getLogger(__name__)


def _find_seed_node(facts: dict, query: str) -> dict | None:
    """Return the node dict whose id or aliases match *query* (case-insensitive for id)."""
    upper = query.strip().upper()
    # Exact id match (case-insensitive)
    for node in facts.get("nodes", []):
        if node["id"].upper() == upper:
            return node
    # Alias match
    for node in facts.get("nodes", []):
        for alias in node.get("aliases", []):
            if alias.strip().upper() == upper or alias.strip() == query.strip():
                return node
    # Curated ticker aliases are part of the canonical lookup contract even
    # when older artifacts were built before aliases were embedded per node.
    canonical = resolve_alias_for_type(query.strip(), "Ticker")
    if canonical:
        for node in facts.get("nodes", []):
            if node.get("type") == "Ticker" and node["id"].upper() == canonical.upper():
                return node
    return None


def retrieve_ticker_subgraph(
    facts: dict,
    ticker: str,
    *,
    hops: int = 2,
    node_types: set[str] | None = None,
    max_edges: int = 80,
) -> dict:
    """Return the *hops*-hop undirected subgraph seeded on *ticker*.

    Args:
        facts:      A ScannerGraphFacts dict (schema_version = scanner_graph_facts.v1).
        ticker:     Ticker symbol or alias to look up.
        hops:       Number of hops to traverse; clamped to [1, 3].
        node_types: Optional set of node types to include (None = all types).
        max_edges:  Maximum edges in the result; BFS-order priority.

    Returns:
        {
            "ticker": canonical_id,
            "nodes": [...],
            "edges": [...],
            "hops": effective_hops,
        }

    Raises:
        KeyError: if ticker (or any alias) is not found in facts.
    """
    hops = max(1, min(int(hops), 3))

    seed = _find_seed_node(facts, ticker)
    if seed is None:
        raise KeyError(
            f"Ticker {ticker!r} not found in scanner graph facts "
            f"(run_id={facts.get('run_id')!r}, scan_date={facts.get('scan_date')!r}). "
            "Check spelling or run rebuild_scanner_graph_facts() to regenerate."
        )
    canonical = seed["id"]

    # Build adjacency: node_id → list of (edge, neighbour_id)
    adjacency: dict[str, list[tuple[dict, str]]] = {}
    for edge in facts.get("edges", []):
        src, tgt = edge["source"], edge["target"]
        adjacency.setdefault(src, []).append((edge, tgt))
        adjacency.setdefault(tgt, []).append((edge, src))

    # BFS
    visited_nodes: dict[str, dict] = {}   # id → node dict
    collected_edges: list[dict] = []
    seen_edge_keys: set[tuple] = set()

    # Index nodes by id for fast lookup
    node_by_id: dict[str, dict] = {n["id"]: n for n in facts.get("nodes", [])}

    queue: deque[tuple[str, int]] = deque([(canonical, 0)])
    visited_nodes[canonical] = seed

    while queue:
        current_id, depth = queue.popleft()
        if depth >= hops:
            continue

        for edge, neighbour_id in adjacency.get(current_id, []):
            # Edge key for dedup
            ekey = (edge["source"], edge["relation"], edge["target"], edge["provenance"])

            if len(collected_edges) >= max_edges:
                break

            if neighbour_id not in visited_nodes:
                neighbour = node_by_id.get(neighbour_id)
                if neighbour is None:
                    continue
                if node_types and neighbour["type"] not in node_types:
                    continue
                visited_nodes[neighbour_id] = neighbour
                queue.append((neighbour_id, depth + 1))

            if ekey not in seen_edge_keys:
                seen_edge_keys.add(ekey)
                collected_edges.append(edge)
                if len(collected_edges) >= max_edges:
                    break

    return {
        "ticker": canonical,
        "nodes": list(visited_nodes.values()),
        "edges": collected_edges,
        "hops": hops,
    }
